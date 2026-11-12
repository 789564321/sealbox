"""SealBox 核心测试（unittest，无第三方依赖）。

运行：python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sealbox.core import job, manifest, password, sfx, verifier  # noqa: E402
from sealbox.core.sevenzip import SevenZip, SevenZipNotFound, add_args, find_sevenzip  # noqa: E402


def sevenzip_available() -> bool:
    try:
        find_sevenzip()
        return True
    except SevenZipNotFound:
        return False


HAS_7Z = sevenzip_available()


class PasswordTests(unittest.TestCase):
    def test_default_is_short22(self) -> None:
        value = password.generate()
        self.assertEqual(len(value), 22)
        self.assertTrue(value.isalnum())

    def test_short22_charset(self) -> None:
        allowed = set(password._SHORT_ALPHABET)
        for _ in range(50):
            value = password.generate("short22")
            self.assertEqual(len(value), 22)
            self.assertTrue(set(value) <= allowed)
            self.assertFalse(set(value) & set("0OIl"))

    def test_hex32_shape(self) -> None:
        value = password.generate("hex32")
        self.assertEqual(len(value), 32)
        int(value, 16)

    def test_uuid_shape(self) -> None:
        value = password.generate("uuid")
        parts = value.split("-")
        self.assertEqual([len(p) for p in parts], [8, 4, 4, 4, 12])
        self.assertEqual(parts[2][0], "4")

    def test_uuid_rand_shape(self) -> None:
        self.assertEqual(len(password.generate("uuid+rand")), 64)

    def test_mixed62_shape(self) -> None:
        value = password.generate("mixed62")
        self.assertEqual(len(value), 32)
        self.assertTrue(value.isalnum())
        self.assertTrue(any(c.islower() for c in value))
        self.assertTrue(any(c.isupper() for c in value))
        self.assertTrue(any(c.isdigit() for c in value))

    def test_unique_many(self) -> None:
        values = {password.generate("hex32") for _ in range(2000)}
        self.assertEqual(len(values), 2000)

    def test_bad_style(self) -> None:
        with self.assertRaises(ValueError):
            password.generate("nope")


class CommandTests(unittest.TestCase):
    def test_default_format_is_zip(self) -> None:
        self.assertEqual(job.JobOptions().formats, ("zip",))

    def test_7z_args(self) -> None:
        args = add_args("7z", Path("out.7z"), [Path("a.txt")], "abc123")
        self.assertIn("-t7z", args)
        self.assertIn("-mhe=on", args)
        self.assertIn("-pabc123", args)
        self.assertEqual(args[-1], "a.txt")

    def test_zip_args(self) -> None:
        args = add_args("zip", Path("out.zip"), [Path("a.txt")], "abc123")
        self.assertIn("-tzip", args)
        self.assertIn("-mem=AES256", args)
        self.assertNotIn("-mhe=on", args)

    def test_bad_format(self) -> None:
        with self.assertRaises(ValueError):
            add_args("rar", Path("x"), [Path("a")], "x")


class ManifestTests(unittest.TestCase):
    def test_render_and_parse(self) -> None:
        options = job.JobOptions(formats=("7z",), pwd_style="hex32")
        task = job.Task(inputs=[Path("a.txt")], options=options, pw_text="deadbeef")
        task.pwd_file = Path("a.密码.txt")
        text = manifest.render(
            task,
            [
                {
                    "name": "a.7z",
                    "fmt_label": "7z",
                    "size": 10,
                    "sha256": "f" * 64,
                    "command": '7z x -p"密码" "a.7z"',
                }
            ],
        )
        self.assertIn("a.7z", text)
        self.assertIn("deadbeef", text)
        self.assertEqual(manifest.extract_pw(text), "deadbeef")


class SfxStubTests(unittest.TestCase):
    def test_offset_matches_stub_length(self) -> None:
        stub = sfx.build_stub()
        marker = b"OFFSET="
        start = stub.index(marker) + len(marker)
        offset = int(stub[start:start + 12])
        self.assertEqual(offset, len(stub))

    def test_build_unix_sfx(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "payload.7z"
            archive.write_bytes(b"FAKE-ARCHIVE-DATA")
            dest = Path(tmp) / "demo.command"
            sfx.make_unix_sfx(archive, dest)
            data = dest.read_bytes()
            stub = sfx.build_stub()
            self.assertTrue(data.startswith(b"#!/bin/bash"))
            self.assertTrue(data.endswith(b"FAKE-ARCHIVE-DATA"))
            self.assertEqual(len(data), len(stub) + len(b"FAKE-ARCHIVE-DATA"))


@unittest.skipUnless(HAS_7Z, "需要安装 7-Zip")
class RoundTripTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="sealbox-test-"))
        self.src = self.tmp / "输入"
        (self.src / "子目录 空格").mkdir(parents=True)
        (self.src / "hello.txt").write_text("hello sealbox\n", encoding="utf-8")
        (self.src / "子目录 空格" / "中文文件.txt").write_text("中文内容\n", encoding="utf-8")
        self.out = self.tmp / "输出"
        self.home = self.tmp / "home"
        os.environ["SEALBOX_HOME"] = str(self.home)

    def tearDown(self) -> None:
        os.environ.pop("SEALBOX_HOME", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, formats: tuple[str, ...]) -> job.Task:
        options = job.JobOptions(formats=formats, output_dir=self.out, verify=True)
        task = job.plan_task([self.src], options)
        job.execute_task(task, sz=SevenZip(find_sevenzip()))
        return task

    def test_all_formats_roundtrip(self) -> None:
        task = self._run(("7z", "zip", "sfx"))
        self.assertEqual(task.state, job.STATE_DONE, task.error)
        names = {p.suffix for p in task.outputs}
        self.assertEqual(len(task.outputs), 3)
        self.assertIn(".7z", names)
        self.assertIn(".zip", names)
        self.assertIn(".exe", names)
        self.assertIsNotNone(task.pwd_file)
        self.assertTrue(task.pwd_file.is_file())

        text = task.pwd_file.read_text(encoding="utf-8")
        self.assertEqual(manifest.extract_pw(text), task.pw_text)

        sz = SevenZip(find_sevenzip())
        for archive in task.outputs:
            target = self.tmp / f"解压-{archive.suffix.strip('.')}"
            ok, hint = verifier.extract_archive(sz, archive, target, task.pw_text)
            self.assertTrue(ok, hint)
            extracted = target / self.src.name / "hello.txt"
            self.assertTrue(extracted.is_file(), extracted)
            self.assertEqual(extracted.read_text(encoding="utf-8"), "hello sealbox\n")

    def test_wrong_pw_fails(self) -> None:
        task = self._run(("7z",))
        sz = SevenZip(find_sevenzip())
        ok, _ = verifier.test_archive(sz, task.outputs[0], "0" * 32)
        self.assertFalse(ok)

    def test_history_recorded(self) -> None:
        from sealbox.core import history

        task = self._run(("7z",))
        rows = history.load()
        self.assertTrue(rows)
        latest = rows[0]
        self.assertEqual(latest["pw"], task.pw_text)
        self.assertEqual(latest["outputs"][0]["name"], task.outputs[0].name)

    def test_no_overwrite(self) -> None:
        task = self._run(("7z",))
        first = task.outputs[0]
        options = job.JobOptions(formats=("7z",), output_dir=self.out, verify=False)
        second = job.plan_task([self.src], options)
        job.execute_task(second, sz=SevenZip(find_sevenzip()))
        self.assertNotEqual(second.outputs[0], first)
        self.assertTrue(first.exists() and second.outputs[0].exists())

    def test_custom_base_name(self) -> None:
        options = job.JobOptions(
            formats=("zip",), output_dir=self.out, base_name="自定义包名", verify=False
        )
        task = job.plan_task([self.src], options)
        job.execute_task(task, sz=SevenZip(find_sevenzip()))
        self.assertEqual(task.state, job.STATE_DONE, task.error)
        self.assertEqual(task.outputs[0].name, "自定义包名.zip")


if __name__ == "__main__":
    unittest.main()

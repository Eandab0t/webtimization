import os
import sys
import json
import tempfile


def test_optimize_writes_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a test file
        test_file = os.path.join(tmpdir, "test.html")
        with open(test_file, "w") as f:
            f.write("<html><head><title>Test</title></head><body>Hello</body></html>")

        from arachni_opt.cli import process_file

        results = process_file(test_file, tmpdir, ["brotli", "gzip"])

        assert os.path.exists(test_file + ".br"), "Brotli sidecar should exist"
        assert os.path.exists(test_file + ".gz"), "Gzip sidecar should exist"
        assert results["original"] > 0
        assert "brotli" in results["compressed"]
        assert "gzip" in results["compressed"]


def test_bench_produces_report():
    import tempfile
    from click.testing import CliRunner
    from arachni_opt.cli import bench

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "sample.html")
        with open(test_file, "w") as f:
            f.write("<html><head><title>Bench Test</title></head><body><p>Content</p></body></html>")

        bench_dir = os.path.join(tmpdir, "bench_output")
        report_path = os.path.join(bench_dir, "report.json")

        runner = CliRunner()
        result = runner.invoke(bench, ["-i", tmpdir, "-o", bench_dir, "--report", report_path])

        assert result.exit_code == 0
        assert os.path.exists(report_path)

        with open(report_path) as f:
            report = json.load(f)

        assert report["total_files"] >= 1
        assert "sample.html" in report["per_file"]


if __name__ == "__main__":
    test_optimize_writes_files()
    test_bench_produces_report()
    print("All tests passed!")

# tests/test_gitstatus.py
import subprocess


def test_tree_finds_modified_file(git_repo):
    """用 app.run_test() 内的 App 上下文创建 GitStatusTree。"""
    import pytest
    from textual.app import App, ComposeResult
    from gitstatus import GitStatusTree

    class _Host(App):
        def __init__(self, path):
            super().__init__()
            self._path = path

        def compose(self) -> ComposeResult:
            yield GitStatusTree(self._path)

    @pytest.mark.asyncio
    async def run():
        (git_repo / "a.txt").write_text("v1")
        subprocess.run(["git", "add", "."], cwd=git_repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"],
                       cwd=git_repo, check=True)
        (git_repo / "a.txt").write_text("v2")

        app = _Host(str(git_repo))
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            tree = app.query_one(GitStatusTree)
            status = tree.get_status(str(git_repo / "a.txt"))
            assert "M" in status

    import asyncio
    asyncio.run(run())
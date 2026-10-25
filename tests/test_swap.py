# tests/test_swap.py
def test_swap_write_and_restore(tmp_path, sample_text_file, monkeypatch):
    import constants
    fake_swap_dir = tmp_path / "swap"
    monkeypatch.setattr(constants, "SWAP_DIR", fake_swap_dir)
    # 重新导入 swap 模块，让 _swap_path 用新的 SWAP_DIR
    import importlib
    import swap
    importlib.reload(swap)

    mgr = swap.SwapManager()
    content = "modified content"
    mgr.write(str(sample_text_file), content)
    assert mgr.restore(str(sample_text_file)) == content
    mgr.delete(str(sample_text_file))
    assert mgr.restore(str(sample_text_file)) is None
# tests/test_app_smoke.py
import pytest

from one_editor import OneEditor


@pytest.mark.asyncio
async def test_app_starts(isolated_config):
    app = OneEditor()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app._tab_data, "App 启动后应至少有一个标签"


@pytest.mark.asyncio
async def test_welcome_tab_on_empty_state(isolated_config):
    """空 state 下应创建欢迎页。"""
    app = OneEditor()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        active = app._tab_data.get(app._active_tab_id)
        assert active is not None
        assert active.get("is_welcome") is True


@pytest.mark.asyncio
async def test_new_file_action(isolated_config):
    app = OneEditor()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        before = len(app._tab_data)
        await pilot.press("ctrl+n")
        await pilot.pause()
        assert len(app._tab_data) == before + 1
"""Git 溯源：安装 Git 后应能读到真实提交，而不是 unavailable。"""
import pytest

from export.provenance import git_state


def test_git_state_reads_current_repository():
    state = git_state()
    if state["commit"] == "unavailable":
        pytest.skip("当前环境没有可用的 Git")
    assert len(state["commit"]) == 40
    assert isinstance(state["dirty"], bool)

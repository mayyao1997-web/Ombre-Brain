from discord_intents import should_notify_may


def test_explicit_may_notification_requests():
    assert should_notify_may("帮我叫一下 May")
    assert should_notify_may("请通知 May")
    assert should_notify_may("喊May")
    assert should_notify_may("呼唤 May")


def test_memory_queries_do_not_notify_may():
    assert not should_notify_may("请从长期记忆中查找 May’s Coffee")
    assert not should_notify_may("找 May's Coffee 的记录")
    assert not should_notify_may("May’s Coffee 是什么")
    assert not should_notify_may("查找 May")
    assert not should_notify_may("告诉我 May 的资料")

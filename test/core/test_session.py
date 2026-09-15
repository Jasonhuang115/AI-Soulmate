from asm.core.session import Session


def test_interrupt_keeps_only_spoken_sentences() -> None:
    session = Session()
    turn_id = session.begin_turn()
    session.append_user("等等")
    session.record_sentence(turn_id, 0, "我想说的是前半句。")
    session.record_sentence(turn_id, 1, "后面你其实没听到。")
    session.append_assistant_spoken(turn_id, 0)
    session.mark_interrupted(turn_id)

    assert session.messages[-1].role == "assistant"
    assert session.messages[-1].content == "我想说的是前半句。 [被打断]"
    assert "后面" not in session.messages[-1].content


def test_drop_matching_prefix_only_when_snapshot_matches() -> None:
    session = Session()
    session.append_user("一")
    session.append_user("二")
    session.append_user("三")
    session.drop_matching_prefix(2, expected=tuple(session.messages[:2]))
    assert [m.content for m in session.messages] == ["三"]
    session.drop_matching_prefix(1, expected=())
    assert [m.content for m in session.messages] == ["三"]


def test_interrupt_with_nothing_spoken() -> None:
    session = Session()
    turn_id = session.begin_turn()
    session.record_sentence(turn_id, 0, "还没播出来。")
    session.mark_interrupted(turn_id)
    assert session.messages[-1].content == "[被打断]"

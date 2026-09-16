from embodiment.gestures import infer_motion


def test_infer_motion_from_chinese() -> None:
    assert infer_motion("挥挥手跟我打招呼") == "wave"
    assert infer_motion("你点点头") == "nod"
    assert infer_motion("摇头") == "shake_head"
    assert infer_motion("给她鼓鼓掌") == "clap"


def test_infer_motion_from_marker() -> None:
    assert infer_motion("请⟦wave⟧一下") == "wave"
    assert infer_motion("来[nod]") == "nod"


def test_infer_motion_ignores_plain_chat() -> None:
    assert infer_motion("今天天气不错") is None
    assert infer_motion("我有点高兴") is None

import reamind


def test_version_is_string():
    assert isinstance(reamind.__version__, str)
    assert reamind.__version__

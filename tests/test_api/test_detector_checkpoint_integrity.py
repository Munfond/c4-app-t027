"""Downloads fail closed on content changes, including already cached artifacts."""
import hashlib
import io

import pytest

from scripts import fetch_detector_checkpoint as fetcher


def test_changed_existing_checkpoint_is_not_replaced(tmp_path, monkeypatch):
    monkeypatch.setitem(fetcher.CONTENT_SHA256, 'lidar', hashlib.sha256(b'expected').hexdigest())
    path = tmp_path / fetcher.MODELS['lidar']
    path.write_bytes(b'changed')
    with pytest.raises(ValueError, match='Existing checkpoint content mismatch'):
        fetcher.fetch('lidar', tmp_path)
    assert path.read_bytes() == b'changed'
    assert not (tmp_path / 'lidar-checkpoint.json').exists()


def test_full_content_pin_required_before_atomic_promotion(tmp_path, monkeypatch):
    monkeypatch.setitem(fetcher.CONTENT_SHA256, 'lidar', hashlib.sha256(b'expected').hexdigest())

    class Response(io.BytesIO):
        headers = {'Content-Length': '7'}

    monkeypatch.setattr(fetcher.urllib.request, 'urlopen', lambda *args, **kwargs: Response(b'changed'))
    with pytest.raises(ValueError, match='does not match pinned content'):
        fetcher.fetch('lidar', tmp_path)
    assert not (tmp_path / fetcher.MODELS['lidar']).exists()
    assert (tmp_path / (fetcher.MODELS['lidar'] + '.part')).read_bytes() == b'changed'

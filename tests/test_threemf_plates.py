"""Tests for multi-plate Bambu/Orca 3MF detection + plates API."""

import zipfile

import pytest

from app.services import threemf_plates
from tests.conftest import insert_test_model

_MODEL_SETTINGS = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <object id="1"><metadata key="name" value="part_a"/></object>
  <object id="2"><metadata key="name" value="part_b"/></object>
  <plate>
    <metadata key="plater_id" value="1"/>
    <metadata key="plater_name" value="Plate One"/>
    <metadata key="thumbnail_file" value="Metadata/plate_1.png"/>
    <model_instance><metadata key="object_id" value="1"/><metadata key="instance_id" value="0"/></model_instance>
    <model_instance><metadata key="object_id" value="2"/><metadata key="instance_id" value="0"/></model_instance>
  </plate>
  <plate>
    <metadata key="plater_id" value="2"/>
    <metadata key="plater_name" value="Plate Two"/>
    <metadata key="thumbnail_file" value="Metadata/plate_2.png"/>
    <model_instance><metadata key="object_id" value="2"/><metadata key="instance_id" value="1"/></model_instance>
  </plate>
</config>"""

_PNG1 = b"\x89PNG\r\n\x1a\nPLATEONE"
_PNG2 = b"\x89PNG\r\n\x1a\nPLATETWO"


def make_multiplate_3mf(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("3D/3dmodel.model", "<model><resources/></model>")
        z.writestr("Metadata/model_settings.config", _MODEL_SETTINGS)
        z.writestr("Metadata/plate_1.png", _PNG1)
        z.writestr("Metadata/plate_2.png", _PNG2)
    return str(path)


def make_plain_3mf(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("3D/3dmodel.model", "<model><resources/></model>")
    return str(path)


@pytest.mark.asyncio
class TestInspect3mf:
    async def test_multiplate_detected(self, tmp_path):
        p = make_multiplate_3mf(tmp_path / "project.3mf")
        info = threemf_plates.inspect_3mf(p)
        assert info["kind"] == "bambu_project"
        assert info["plate_count"] == 2
        assert [pl["plater_id"] for pl in info["plates"]] == [1, 2]
        assert info["plates"][0]["name"] == "Plate One"
        assert info["plates"][0]["object_ids"] == [1, 2]
        assert info["plates"][0]["thumbnail"] == "Metadata/plate_1.png"

    async def test_plain_3mf(self, tmp_path):
        p = make_plain_3mf(tmp_path / "plain.3mf")
        info = threemf_plates.inspect_3mf(p)
        assert info["kind"] == "plain_3mf"
        assert info["plate_count"] == 1
        assert info["plates"] == []

    async def test_corrupt_file(self, tmp_path):
        p = tmp_path / "bad.3mf"
        p.write_bytes(b"not a zip")
        info = threemf_plates.inspect_3mf(str(p))
        assert info["kind"] == "plain_3mf"
        assert info["plate_count"] == 1

    async def test_read_plate_thumbnail(self, tmp_path):
        p = make_multiplate_3mf(tmp_path / "project.3mf")
        info = threemf_plates.inspect_3mf(p)
        data, ctype = threemf_plates.read_plate_thumbnail(p, info["plates"][0])
        assert data == _PNG1
        assert ctype == "image/png"
        data2, _ = threemf_plates.read_plate_thumbnail(p, info["plates"][1])
        assert data2 == _PNG2


@pytest.mark.asyncio
class TestPlatesApi:
    async def test_plates_endpoint(self, client, tmp_path):
        p = make_multiplate_3mf(tmp_path / "api.3mf")
        mid = await insert_test_model(
            client._db_path, name="proj", file_path=p, file_format="3MF"
        )
        r = await client.get(f"/api/models/{mid}/plates")
        assert r.status_code == 200
        body = r.json()
        assert body["plate_count"] == 2
        assert body["plates"][0]["index"] == 0
        assert body["plates"][0]["has_thumbnail"] is True

    async def test_plate_thumbnail_endpoint(self, client, tmp_path):
        p = make_multiplate_3mf(tmp_path / "api2.3mf")
        mid = await insert_test_model(
            client._db_path, name="proj2", file_path=p, file_format="3MF"
        )
        r = await client.get(f"/api/models/{mid}/plates/1/thumbnail")
        assert r.status_code == 200
        assert r.content == _PNG2
        assert r.headers["content-type"] == "image/png"

    async def test_plate_thumbnail_out_of_range(self, client, tmp_path):
        p = make_multiplate_3mf(tmp_path / "api3.3mf")
        mid = await insert_test_model(
            client._db_path, name="proj3", file_path=p, file_format="3MF"
        )
        r = await client.get(f"/api/models/{mid}/plates/9/thumbnail")
        assert r.status_code == 404

    async def test_plates_non_3mf(self, client):
        mid = await insert_test_model(client._db_path, name="stl", file_path="/m/x.stl")
        r = await client.get(f"/api/models/{mid}/plates")
        assert r.json()["plate_count"] == 1

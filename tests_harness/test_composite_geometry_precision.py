import geopandas as gpd
from shapely.geometry import Polygon

from harness.grader import grade_criterion


def test_geometry_roundoff_is_accepted_but_material_shift_is_rejected(tmp_path):
    workspace=tmp_path/'workspace';workspace.mkdir()
    reference=tmp_path/'expected.gpkg'
    gpd.GeoDataFrame({'id':[1]},geometry=[Polygon([(0,0),(10,0),(10,10),(0,10)])],crs='EPSG:32649').to_file(reference)
    criterion={'type':'vector_match','target':'basin.gpkg','reference':'expected.gpkg',
        'atol':1e-6,'rtol':1e-6,'geometry_tolerance':1e-6}
    for shift,accepted in [(4.8e-10,True),(0.01,False)]:
        target=workspace/'basin.gpkg'
        if target.exists():target.unlink()
        gpd.GeoDataFrame({'id':[1]},geometry=[Polygon([(shift,0),(10+shift,0),(10+shift,10),(shift,10)])],crs='EPSG:32649').to_file(target)
        result=grade_criterion(criterion,workspace,tmp_path)
        assert (result['score']==1.0)==accepted

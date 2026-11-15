"""Проверки native чтения и сохранения геометрии без доступа к Earthdata."""
import h5py
import numpy as np
import pytest

from scripts.download_mexico_remaining import samples, geometry_cube, inventory


def test_inventory_has_exactly_38_additional_source_ids():
    catalogue,existing,remaining=inventory()
    assert len(catalogue['granules'])==54 and len(existing)==16 and len(remaining)==38
    assert all(g['id'] not in existing for g in remaining)


def test_native_sampling_keeps_integer_masks_and_rejects_outside(tmp_path):
    with h5py.File(tmp_path/'fixture.h5','w') as h:
        g=h.create_group('grid');g['xCoordinates']=[0.,1.,2.];g['yCoordinates']=[2.,1.,0.];g['projection']=4326
        g['phase']=np.arange(9,dtype=float).reshape(3,3);g['phase'].attrs['_FillValue']=4.
        g['mask']=np.arange(9,dtype=np.uint32).reshape(3,3)
        a,meta=samples(g,{'phase':'phase','mask':'mask'},np.array([[2.,1.]]),np.array([[0.,1.]]))
        assert a['phase'][0,0]==0 and np.isnan(a['phase'][0,1])
        assert a['mask'].dtype==np.uint32 and a['mask'][0,1]==4
        assert meta['window']==[0,2,0,2]
        with pytest.raises(ValueError,match='пределами'):
            samples(g,{'phase':'phase'},np.array([[5.]]),np.array([[5.]]))


def test_geometry_preserves_all_height_planes_without_assumed_height(tmp_path):
    with h5py.File(tmp_path/'geometry.h5','w') as h:
        assert geometry_cube(h,np.array([[1.]]),np.array([[1.]]))[1]['available'] is False
        g=h.create_group('science/LSAR/GUNW/metadata/radarGrid')
        g['xCoordinates']=[0.,1.,2.];g['yCoordinates']=[2.,1.,0.];g['projection']=4326
        g['heightAboveEllipsoid']=[0.,2000.,3000.]
        g['losUnitVectorX']=np.full((3,3,3),-.4);g['losUnitVectorY']=np.full((3,3,3),.1)
        a,meta=geometry_cube(h,np.array([[1.]]),np.array([[1.]]))
        assert meta['available'] and a['geometry_los_e'].shape==(3,3,3)
        np.testing.assert_array_equal(a['geometry_height'],[0,2000,3000])

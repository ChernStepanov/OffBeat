"""Isolated numerical fixtures only; never exported as application data."""
import tempfile
import unittest
from pathlib import Path
import h5py
import numpy as np
from pyproj import Transformer
from prepare_nisar import sample, db

class ExtractionTests(unittest.TestCase):
    def test_power_and_missing(self):
        self.assertEqual(db(1), 0)
        self.assertEqual(db(.1), -10)
        self.assertIsNone(db(0))
        self.assertIsNone(db(-1))
        self.assertIsNone(db(None))

    def test_native_grid_fill_and_bounds(self):
        with tempfile.TemporaryDirectory() as temporary:
            with h5py.File(Path(temporary)/'fixture.h5','w') as hdf:
                group=hdf.create_group('grid')
                group['projection']=32614
                group['xCoordinates']=[490000.,490010.]
                group['yCoordinates']=[2150000.,2149990.]
                ds=group.create_dataset('HHHH',data=np.array([[1.,-9999.],[np.nan,.1]]))
                ds.attrs['_FillValue']=-9999.
                transform=Transformer.from_crs(32614,4326,always_xy=True)
                def read(x,y):
                    lon,lat=transform.transform(x,y)
                    return sample(group,'HHHH',lat,lon)
                self.assertEqual(read(490000.,2150000.),1.)
                self.assertIsNone(read(490010.,2150000.))
                self.assertIsNone(read(490000.,2149990.))
                self.assertIsNone(read(489980.,2150000.))

if __name__=='__main__':
    unittest.main()

"""Read-only ingestion of the supplied basin, time series and event sources."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import pyexpat  # load stdlib before GDAL on Windows
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.merge import merge
from rasterio.warp import reproject, Resampling, calculate_default_transform
from composite_common import ROOT, LUMPED, SEMI, sha, write_json

EVENTS = ['20140409','20150509','20191031','20230908','20241030','20250627']
STATIONS = {'东方':'DF','七差':'QC','白晶':'BJ','公爱':'GA','乌烈':'WL','戈枕坝上':'GZ','广坝上':'GB'}

def csv(path, frame):
    path=Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path,index=False,float_format='%.12g',lineterminator='\n')

def supplemented(frame, label):
    """Preserve known observations; additions are benchmark synthetic, not repaired truth."""
    out=frame.copy(); records=[]
    out.rename(columns={'Time':'time'},inplace=True)
    out['time']=pd.to_datetime(out.time)
    rng=np.random.default_rng(20261004+sum(map(ord,label)))
    for column in [c for c in out if c.endswith('_rain')]:
        mask=out[column].isna(); values=np.where(rng.random(len(out))<0.16,rng.gamma(1.5,2,len(out)),0)
        for i in np.flatnonzero(mask):records.append({'time':str(out.time.iloc[i]),'column':column,'value':float(values[i]),'basis':'synthetic benchmark supplement; original blank remains unknown'})
        out.loc[mask,column]=values[mask]
    if 'E0' not in out:
        monthly={1:.126,2:.138,3:.165,4:.197,5:.208,6:.197,7:.195,8:.160,9:.136,10:.133,11:.132,12:.126}
        out['E0']=out.time.dt.month.map(monthly)
        records.extend({'time':str(t),'column':'E0','value':float(v),'basis':'provided monthly table, explicitly assumed E0 for this benchmark scenario'} for t,v in zip(out.time,out.E0))
    return out,records

def prepare_shared_inputs():
    dest=ROOT/'composite_assets';dest.mkdir(exist_ok=True)
    source=[]
    for label,root in [('lumped',LUMPED),('semi',SEMI)]:
        for p in sorted(root.rglob('*')):
            if p.is_file():source.append({'dataset':label,'path':p.relative_to(root).as_posix(),'size_bytes':p.stat().st_size,'sha256':sha(p)})
    write_json(dest/'source_manifest.json',{'datasets':source,'source_directories_read_only':True})
    continuous=dest/'continuous_raw.csv'
    if not continuous.exists():
        df=pd.read_excel(next(SEMI.glob('*.xlsx')),usecols=list(range(16)))
        df=df[(pd.to_datetime(df.time)>='2023-08-01')&(pd.to_datetime(df.time)<'2023-09-01')].copy()
        csv(continuous,df)
    raw=pd.read_csv(continuous)
    augmented,records=supplemented(raw,'continuous')
    csv(dest/'continuous_supplemented.csv',augmented);csv(dest/'continuous_supplements.csv',pd.DataFrame(records))
    for event in EVENTS:
        src=LUMPED/'场次洪水数据'/f'{event}.csv';shutil.copyfile(src,dest/f'{event}_raw.csv')
        aug,patch=supplemented(pd.read_csv(src),event)
        csv(dest/f'{event}_supplemented.csv',aug);csv(dest/f'{event}_supplements.csv',pd.DataFrame(patch))
    stations=gpd.read_file(SEMI/'rainfall_stations.shp')
    csv(dest/'stations.csv',pd.DataFrame({'source_id':[STATIONS[n] for n in stations.station],'x':stations.geometry.x,'y':stations.geometry.y}))
    basin=gpd.read_file(SEMI/'boundary.shp');basin.to_file(dest/'basin.gpkg',driver='GPKG')
    # Actual ASTER elevations and full basin are retained; resampling is explicit.
    if not (dest/'dem_100m.tif').exists():
        datasets=[rasterio.open(p) for p in sorted(SEMI.glob('*_dem.tif'))]
        try:
            bounds=basin.total_bounds;buffer=.05
            array,transform=merge(datasets,bounds=(bounds[0]-buffer,bounds[1]-buffer,bounds[2]+buffer,bounds[3]+buffer))
            src_bounds=rasterio.transform.array_bounds(array.shape[1],array.shape[2],transform)
            target,w,h=calculate_default_transform(datasets[0].crs,'EPSG:32649',array.shape[2],array.shape[1],*src_bounds,resolution=100)
            output=np.full((h,w),-9999,dtype='float32')
            reproject(array[0],output,src_transform=transform,src_crs=datasets[0].crs,dst_transform=target,dst_crs='EPSG:32649',dst_nodata=-9999,resampling=Resampling.bilinear)
            with rasterio.open(dest/'dem_100m.tif','w',driver='GTiff',height=h,width=w,count=1,dtype='float32',crs='EPSG:32649',transform=target,nodata=-9999,compress='deflate') as ds:ds.write(output,1)
        finally:
            for ds in datasets:ds.close()
    write_json(dest/'derivation.json',{'seed':20261004,'continuous_window':['2023-08-01','2023-09-01'],'events':EVENTS,'dem':{'source':'four supplied ASTER tiles','resolution_m':100,'crs':'EPSG:32649','resampling':'bilinear','boundary':'unaltered real geometry'},'supplement_semantics':'hybrid benchmark, not recovered observations','flow_semantics':'benchmark assumptions require explicit confirmation, not inferred original facts'})
    return dest

if __name__=='__main__':print(prepare_shared_inputs())

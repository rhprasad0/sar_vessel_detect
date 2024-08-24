#!/usr/bin/env bash

# source this script

s1scene_name=S1A_IW_GRDH_1SDV_20240814T171426_20240814T171451_055212_06BAD3_F4BF.SAFE.zip

s1scene_path=/home/ryan/sar_vessel_detect/s1_safe/$s1scene_name
model_input_folder=/home/ryan/sar_vessel_detect/model_input/1
process_grd=/home/ryan/sar_vessel_detect/xview/process_grd.py
reproject_grd=/home/ryan/sar_vessel_detect/xview/reproject_grd.py
processing_folder=/home/ryan/sar_vessel_detect/processing
bathy_raster_script_path=/home/ryan/sar_vessel_detect/get_bathy_raster.py
bathy_rasters_path=/home/ryan/sar_vessel_detect/bathymetry/rasters


# Clean up previous run
rm -r $processing_folder
rm -r $model_input_folder

mkdir $processing_folder
mkdir $model_input_folder

# Process the S1 image using the xView code
conda activate xview3
python3 $process_grd $s1scene_path
python3 $reproject_grd $processing_folder/${s1scene_name::-4}/${s1scene_name::-4}_Sigma0_VH_LOG.tif
python3 $reproject_grd $processing_folder/${s1scene_name::-4}/${s1scene_name::-4}_Sigma0_VV_LOG.tif
mv $processing_folder/${s1scene_name::-4}/${s1scene_name::-4}_Sigma0_VV_LOG_UTM_10m_16b.tif \
    $model_input_folder/VV_dB.tif
mv $processing_folder/${s1scene_name::-4}/${s1scene_name::-4}_Sigma0_VH_LOG_UTM_10m_16b.tif \
    $model_input_folder/VH_dB.tif
echo
echo "Finished S1 processing"
echo

# Get image footprint
conda activate ships
gdal_footprint $model_input_folder/VH_dB.tif $model_input_folder/footprint.geojson

# Select bathy raster
conda activate gpd # geopandas does not like the repo env
bathy_raster=$(python3 $bathy_raster_script_path)
conda activate ships

# Get EPSG for bathy reproject to UTM
utm_epsg=$(gdalinfo ${model_input_folder}/VH_dB.tif -json | jq -r .stac | jq -r .'["proj:epsg"]')

# Clip bathy raster to S1 extent. Reproject to UTM and set resolution to 500m
gdalwarp -cutline \
    $model_input_folder/footprint.geojson \
    $bathy_rasters_path/$bathy_raster \
    $model_input_folder/bathymetry.tif \
    -t_srs EPSG:$utm_epsg \
    -tr 500 500
echo
echo "Processed bathymetry raster"
echo

# Time for inference!! >8-)
cd ./src
python -m xview3.infer.inference --image_folder ../model_input/ \
    --weights ../data/models/model.pth --output out.csv \
    --config_path ../data/configs/final.txt --padding 400 \
    --window_size 3072 --overlap 20
cd ..
echo
echo "*** Inference complete!!! ***"
echo
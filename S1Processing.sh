#!/usr/bin/env bash

# source this script

s1scene=/home/ryan/sar_vessel_detect/S1A_IW_GRDH_1SDV_20240811T015824_20240811T015853_055159_06B8DF_9183.SAFE.zip
gpt_path=/home/ryan/esa-snap/bin/gpt
processing_folder=/home/ryan/sar_vessel_detect/processing
model_input_folder=/home/ryan/sar_vessel_detect/model_input

# Clean up previous run
rm -r $processing_folder
rm -r $model_input_folder

mkdir $processing_folder
mkdir -p ${model_input_folder}/1 

# Step 1: Apply orbit file
bash $gpt_path Apply-Orbit-File -Ssource=$s1scene \
    -t $processing_folder/orbit1.dim
echo
echo "Step 1: Applied orbit file"
echo

# Step 2: Remove border noise
bash $gpt_path Remove-GRD-Border-Noise -SsourceProduct=$processing_folder/orbit1.dim \
    -t $processing_folder/border2.dim
echo
echo "Step 2: Removed border noise"
echo

# Step 3: Remove thermal noise
bash $gpt_path Remove-GRD-Border-Noise -SsourceProduct=$processing_folder/border2.dim \
    -t $processing_folder/thermal3.dim
echo
echo "Step 3: Removed thermal noise"
echo

# Step 4: Apply radiometric calibration
bash $gpt_path Calibration -Ssource=$processing_folder/thermal3.dim \
    -t $processing_folder/calibration4.dim -PoutputSigmaBand=true
echo
echo "Step 4: Applied radiometric calibration"
echo

# Step 5: Apply terrain correction. Need to use GETASSE for arctic, but not implemented here.
bash $gpt_path Terrain-Correction -Ssource=$processing_folder/calibration4.dim \
    -t $processing_folder/terrain5.dim \
    -PdemName="SRTM 1Sec HGT" \
    -PnodataValueAtSea=false
echo
echo "Step 5: Applied terrain correction"
echo

# Step 6: Convert to logarithmic scale
bash $gpt_path LinearToFromdB -Ssource=$processing_folder/terrain5.dim \
    -t $processing_folder/logarithmic6.dim
echo
echo "Step 6: Converted to logarithmic scale"
echo

# Step 7: Reproject to UTM
bash $gpt_path Reproject -Ssource=$processing_folder/logarithmic6.dim \
    -t $processing_folder/reprojected7.dim \
    -Pcrs=AUTO:42001 \
    -PpixelSizeX=10 \
    -PpixelSizeY=10
echo
echo "Step 7: Reprojected raster"
echo

# Step 8: Convert to GeoTIFF
gdal_translate $processing_folder/reprojected7.data/Sigma0_VH_db.img ${model_input_folder}/1/VH_dB.tif
gdal_translate $processing_folder/reprojected7.data/Sigma0_VV_db.img ${model_input_folder}/1/VV_dB.tif
echo
echo "Step 8: Converted to GeoTIFF"
echo

# Get image footprint
gdal_footprint $processing_folder/logarithmic6.data/Sigma0_VV_db.img ${model_input_folder}/1/footprint.geojson

# Select bathy raster
conda activate gpd # geopandas does not like the repo env
bathy_raster=$(python3 ./get_bathy_raster.py)
conda activate ships

# Get EPSG for bathy reproject to UTM
utm_epsg=$(gdalinfo ${model_input_folder}/1/VH_dB.tif -json | jq -r .stac | jq -r .'["proj:epsg"]')

# Clip bathy raster to S1 extent. Reproject to UTM and set resolution to 500m
gdalwarp -cutline \
    ./model_input/1/footprint.geojson \
    ./bathymetry/rasters/$bathy_raster \
    ./model_input/1/bathymetry.tif \
    -t_srs EPSG:$utm_epsg \
    -tr 500 500
echo
echo "Processed bathymetry raster"
# echo

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
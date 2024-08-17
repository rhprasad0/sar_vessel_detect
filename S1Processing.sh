#!/usr/bin/env bash

s1scene=/home/ryan/sar_vessel_detect/S1A_IW_GRDH_1SDV_20240811T015824_20240811T015853_055159_06B8DF_9183.SAFE.zip
gpt_path=/home/ryan/esa-snap/bin/gpt
processing_folder=/home/ryan/sar_vessel_detect/processing
model_input_folder=/home/ryan/sar_vessel_detect/model_input

# Clean up previous run
rm -r $processing_folder
rm -r $model_input_folder

mkdir $processing_folder
mkdir ${model_input_folder}/1 -p

cd $processing_folder

# Step 1: Apply orbit file
bash $gpt_path Apply-Orbit-File -Ssource=$s1scene \
    -t ./orbit1.dim
echo "Step 1: Applied orbit file"
echo

# Step 2: Remove border noise
bash $gpt_path Remove-GRD-Border-Noise -SsourceProduct=./orbit1.dim \
    -t ./border2.dim
echo "Step 2: Removed border noise"
echo

# Step 3: Remove thermal noise
bash $gpt_path Remove-GRD-Border-Noise -SsourceProduct=./border2.dim \
    -t ./thermal3.dim
echo "Step 3: Removed thermal noise"
echo

# Step 4: Apply radiometric calibration
bash $gpt_path Calibration -Ssource=./thermal3.dim \
    -t ./calibration4.dim -PoutputSigmaBand=true
echo "Step 4: Applied radiometric calibration"
echo

# Step 5: Apply terrain correction
bash $gpt_path Terrain-Correction -Ssource=./calibration4.dim \
    -t ./terrain5.dim \
    -PdemName="SRTM 3Sec" \
    -PnodataValueAtSea=false
echo "Step 5: Applied terrain correction"
echo

# Step 6: Convert to logarithmic scale
bash $gpt_path LinearToFromdB -Ssource=./terrain5.dim \
    -t ./logarithmic6.dim
echo "Step 6: Converted to logarithmic scale"
echo

# Step 7: Reproject to UTM
bash $gpt_path Reproject -Ssource=./logarithmic6.dim \
    -t ./reprojected7.dim \
    -Pcrs=AUTO:42001 \
    -PpixelSizeX=10 \
    -PpixelSizeY=10
echo "Step 7: Reprojected raster"
echo

# Step 8: Convert to GeoTIFF
gdal_translate ./reprojected7.data/Sigma0_VH_db.img ${model_input_folder}/1/VH_db.tif
gdal_translate ./reprojected7.data/Sigma0_VV_db.img ${model_input_folder}/1/VV_db.tif
echo "Step 8: Converted to GeoTIFF"
echo

cd ..


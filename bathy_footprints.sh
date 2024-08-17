#!/usr/bin/env bash

gdal_footprint ./bathymetry/rasters/gebco_2024_sub_ice_n0.0_s-90.0_w-90.0_e0.0.tif ./bathymetry/footprints/gebco_2024_sub_ice_n0.0_s-90.0_w-90.0_e0.0.geojson         
gdal_footprint ./bathymetry/rasters/gebco_2024_sub_ice_n0.0_s-90.0_w-180.0_e-90.0.tif ./bathymetry/footprints/gebco_2024_sub_ice_n0.0_s-90.0_w-180.0_e-90.0.geojson 
gdal_footprint ./bathymetry/rasters/gebco_2024_sub_ice_n0.0_s-90.0_w0.0_e90.0.tif ./bathymetry/footprints/gebco_2024_sub_ice_n0.0_s-90.0_w0.0_e90.0.geojson
gdal_footprint ./bathymetry/rasters/gebco_2024_sub_ice_n0.0_s-90.0_w90.0_e180.0.tif ./bathymetry/footprints/gebco_2024_sub_ice_n0.0_s-90.0_w90.0_e180.0.geojson
gdal_footprint ./bathymetry/rasters/gebco_2024_sub_ice_n90.0_s0.0_w-90.0_e0.0.tif ./bathymetry/footprints/gebco_2024_sub_ice_n90.0_s0.0_w-90.0_e0.0.geojson
gdal_footprint ./bathymetry/rasters/gebco_2024_sub_ice_n90.0_s0.0_w-180.0_e-90.0.tif ./bathymetry/footprints/gebco_2024_sub_ice_n90.0_s0.0_w-180.0_e-90.0.geojson
gdal_footprint ./bathymetry/rasters/gebco_2024_sub_ice_n90.0_s0.0_w0.0_e90.0.tif ./bathymetry/footprints/gebco_2024_sub_ice_n90.0_s0.0_w0.0_e90.0.geojson
gdal_footprint ./bathymetry/rasters/gebco_2024_sub_ice_n90.0_s0.0_w90.0_e180.0.tif ./bathymetry/footprints/gebco_2024_sub_ice_n90.0_s0.0_w90.0_e180.0.geojson
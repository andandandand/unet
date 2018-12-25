#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2018 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: EPL-2.0
#

import os
import nibabel as nib
import numpy as np
from tqdm import tqdm
import h5py
import json

import argparse

parser = argparse.ArgumentParser(
    description="Convert Decathlon raw Nifti data "
    "(http://medicaldecathlon.com/) "
    "files to Numpy data files",
    add_help=True, formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument("--data_path",
                    default="../../data/decathlon/Task01_BrainTumour/",
                    help="Path to the raw BraTS datafiles")
parser.add_argument("--save_path",
                    default="../../data/decathlon/",
                    help="Folder to save Numpy data files")
parser.add_argument("--output_filename",
                    default="decathlon_brats.h5",
                    help="Name of the output HDF5 file")
parser.add_argument("--resize", type=int, default=144,
                    help="Resize height and width to this size. "
                    "Original size = 240")
parser.add_argument("--split", type=float, default=0.85,
                    help="Train/test split ratio")

args = parser.parse_args()

def crop_center(img, cropx, cropy, cropz):
    """
    Take a center crop of the images.
    If we are using a 2D model, then we'll just stack the
    z dimension.
    """

    if len(img.shape) == 4:
        x, y, z, c = img.shape
    else:
        x, y, z = img.shape

    # Make sure starting index is >= 0
    startx = max(x//2-(cropx//2), 0)
    starty = max(y//2-(cropy//2), 0)
    startz = max(z//2-(cropz//2), 0)

    # Make sure ending index is <= size
    endx = min(startx + cropx, x)
    endy = min(starty + cropy, y)
    endz = min(startz + cropz, z)

    if len(img.shape) == 4:
        return img[startx:endx, starty:endy, startz:endz, :]
    else:
        return img[startx:endx, starty:endy, startz:endz]


def normalize_img(img):
    """
    Normalize the pixel values.
    This is one of the most important preprocessing steps.
    We need to make sure that the pixel values have a mean of 0
    and a standard deviation of 1 t0 help the model to train
    faster and more accurately.
    """

    for channel in range(img.shape[3]):
        img[:, :, :, channel] = (
            img[:, :, :, channel] - np.mean(img[:, :, :, channel])) \
            / np.std(img[:, :, :, channel])

    return img


def convert_raw_data_to_hdf5(trainIdx, validateIdx, fileIdx, 
                             filename, dataDir, json_data):

    """
    Go through the Decathlon dataset.json file.
    We've already split into training and validation subsets.
    Read in Nifti format files. Crop images and masks.
    Save to HDF5 format.
    """
    hdf_file = h5py.File(filename, "w")
   
    # Save information about the Decathlon dataset
    dt = h5py.special_dtype(vlen=str)
    license = hdf_file.create_dataset("license", (100,), dtype=dt)
    license = json_data["licence"] # sic
    
    dataset_name = hdf_file.create_dataset("name", (100,), dtype=dt)
    dataset_name = json_data["name"]
    
    description = hdf_file.create_dataset("description", (200,), dtype=dt)
    description = json_data["description"]
    
    reference = hdf_file.create_dataset("reference", (100,), dtype=dt)
    reference = json_data["reference"]
    
    release = hdf_file.create_dataset("release", (50,), dtype=dt)
    release = json_data["release"]

    # Save training set images
    print("Step 1 of 4. Save training set images.")
    first = True
    for idx in tqdm(trainIdx):

        data_filename = os.path.join(dataDir, fileIdx[idx]["image"])
        img = np.array(nib.load(data_filename).dataobj)
        img = crop_center(img, args.resize, args.resize, args.resize)
        img = normalize_img(img)

        img = np.swapaxes(np.array(img), 0, -2)
        num_rows = img.shape[0]

        if first:
            first = False
            img_train_dset = hdf_file.create_dataset("imgs_train",
                                                     img.shape,
                                                     maxshape=(None, img.shape[1],
                                                               img.shape[2], img.shape[3]),
                                                     dtype=float, compression="gzip")
            img_train_dset[:] = img
        else:
            row = img_train_dset.shape[0]  # Count current dataset rows
            img_train_dset.resize(row+num_rows, axis=0)  # Add new row
            img_train_dset[row:(row+num_rows), :] = img  # Insert data into new row

    hdf_file["imgs_train"].attrs["modalities"] = json_data["modalities"]

    # Save validaition set images
    print("Step 2 of 4. Save validation set images.")
    first = True
    for idx in tqdm(validateIdx):

        # Nibabel should read the file as X,Y,Z,C
        data_filename = os.path.join(dataDir, fileIdx[idx]["image"])
        img = np.array(nib.load(data_filename).dataobj)
        img = crop_center(img, args.resize, args.resize, args.resize)
        img = normalize_img(img)

        img = np.swapaxes(np.array(img), 0, -2)
        num_rows = img.shape[0]

        if first:
            first = False
            img_test_dset = hdf_file.create_dataset("imgs_test",
                                                    img.shape,
                                                    maxshape=(None, img.shape[1],
                                                              img.shape[2], img.shape[3]),
                                                    dtype=float, compression="gzip")
            img_test_dset[:] = img
        else:
            row = img_test_dset.shape[0]  # Count current dataset rows
            img_test_dset.resize(row+num_rows, axis=0)  # Add new row
            img_test_dset[row:(row+num_rows), :] = img  # Insert data into new row

    hdf_file["imgs_test"].attrs["modalities"] = json_data["modalities"]
    
    # Save training set masks
    print("Step 3 of 4. Save training set masks.")
    first = True
    for idx in tqdm(trainIdx):

        data_filename = os.path.join(dataDir, fileIdx[idx]["label"])
        msk = np.array(nib.load(data_filename).dataobj)
        msk = crop_center(msk, args.resize, args.resize, args.resize)

        msk[msk > 1] = 1  # Combine all masks
        msk = np.expand_dims(np.swapaxes(np.array(msk), 0, -1), -1)
        num_rows = msk.shape[0]

        if first:
            first = False
            msk_train_dset = hdf_file.create_dataset("msks_train",
                                                     msk.shape,
                                                     maxshape=(None, msk.shape[1],
                                                               msk.shape[2], msk.shape[3]),
                                                     dtype=float, compression="gzip")
            msk_train_dset[:] = msk
        else:
            row = msk_train_dset.shape[0]  # Count current dataset rows
            msk_train_dset.resize(row+num_rows, axis=0)  # Add new row
            msk_train_dset[row:(row+num_rows), :] = msk  # Insert data into new row

    # Save testing/validation set masks

    print("Step 4 of 4. Save validation set masks.")
    first = True
    for idx in tqdm(validateIdx):

        data_filename = os.path.join(dataDir, fileIdx[idx]["label"])
        msk = np.array(nib.load(data_filename).dataobj)
        msk = crop_center(msk, args.resize, args.resize, args.resize)

        msk[msk > 1] = 1  # Combine all masks
        msk = np.expand_dims(np.swapaxes(np.array(msk), 0, -1), -1)
        num_rows = msk.shape[0]

        if first:
            first = False
            msk_test_dset = hdf_file.create_dataset("msks_test",
                                                    msk.shape,
                                                    maxshape=(None, msk.shape[1],
                                                              msk.shape[2], msk.shape[3]),
                                                    dtype=float, compression="gzip")
            msk_test_dset[:] = msk
        else:
            row = msk_test_dset.shape[0]  # Count current dataset rows
            msk_test_dset.resize(row+num_rows, axis=0)  # Add new row
            msk_test_dset[row:(row+num_rows), :] = msk  # Insert data into new row

    print("Finished processing.")
    print("HDF5 saved to {}".format(filename))

if __name__ == "__main__":

    print("Converting Decathlon raw Nifti data files to single "
          "training and validation HDF5 data file.")
    print(args)

    save_dir = os.path.join(
        args.save_path, "{}x{}/".format(args.resize, args.resize))

    # Create directory
    try:
        os.makedirs(save_dir)
    except OSError:
        if not os.path.isdir(save_dir):
            raise

    filename = os.path.join(save_dir, args.output_filename)
    # Check for existing output file and delete if exists
    if os.path.exists(filename):
        print("Removing existing data file: {}".format(filename))
        os.remove(filename)


    """
    Get the training file names from the data directory.
    Decathlon should always have a dataset.json file in the
    subdirectory which lists the experiment information including
    the input and label filenames.
    """

    json_filename = os.path.join(args.data_path, "dataset.json")

    try:
        with open(json_filename, "r") as fp:
            experiment_data = json.load(fp)
    except IOError as e:
        print("File {} doesn't exist. It should be part of the "
              "Decathlon directory".format(json_filename))

    # Print information about the Decathlon experiment data
    print("Dataset name = ", experiment_data["name"])
    print(experiment_data["description"])
    print("Dataset release: ", experiment_data["release"])
    print("Dataset reference: ", experiment_data["reference"])
    print("Dataset license: ", experiment_data["licence"]) # sic
    
    print("="*30)
    print("="*30)
    
    """
    Randomize the file list. Then separate into training and
    validation (testing) lists.
    """
    # Set the random seed so that always get same random mix
    np.random.seed(816)
    numFiles = experiment_data["numTraining"]
    idxList = np.arange(numFiles)  # List of file indices
    randomList = np.random.random((numFiles)) # List of random numbers
    # Random number go from 0 to 1. So anything above 
    # args.train_split is in the validation list.
    trainList = idxList[randomList < args.split]  
    validateList = idxList[randomList >= args.split]


    convert_raw_data_to_hdf5(trainList, validateList,
                             experiment_data["training"],
                             filename, args.data_path,
                             experiment_data)
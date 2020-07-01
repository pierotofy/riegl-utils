import argparse
import subprocess
import os
import glob
import tempfile
import datetime
import json
import shutil
import csv
import numpy as np
from gwpy.time import tconvert
from scipy.interpolate import interp1d
from PIL import Image
import piexif

parser = argparse.ArgumentParser(description='Trajectory to GPS')
parser.add_argument('--crs', '-c',
                    metavar='<string>',
                    required=True,
                    help='EPSG code of trajectory values (EPSG:xxxx)')
parser.add_argument('--input', '-i',
                    metavar='<path>',
                    required=True,
                    help='Path of images to augment with trajectory')
parser.add_argument('--trajectory', '-t',
                    metavar='<path>',
                    required=True,
                    help='Path of trajectory file')
parser.add_argument('--interpolation', '-interp',
                    metavar='<string>',
                    required=False,
                    choices=['linear', 'quadratic', 'cubic'],
                    default='linear',
                    help='Interpolation method for trajectory points. %(default)s')

# parser.add_argument('amount',
#                     metavar='<pixel|percentage%>',
#                     type=str,
#                     help='Pixel of largest side or percentage to resize images by')
args = parser.parse_args()

ddb_path = shutil.which('ddb')
if ddb_path is None:
    die("ddb not found. Is DroneDB installed?")

exiftool_path = shutil.which('exiftool')
if exiftool_path is None:
    die("exiftool not found. Is it installed?")

def die(msg):
    print("ERR: %s" % msg)
    exit(1)

files = []
if os.path.isdir(args.input):
    for ext in ["JPG", "JPEG", "PNG", "TIFF", "TIF"]:
        files += glob.glob("{}/*.{}".format(args.input, ext))
        files += glob.glob("{}/*.{}".format(args.input, ext.lower()))
elif os.path.exists(args.input):
    files = [args.input]
else:
    die("{} does not exist".format(args.input))

def ddb(*args):
    subprocess.run([ddb_path] + list(args))

def exiftool(*args):
    return subprocess.check_output([exiftool_path] + list(args)).decode('utf8')

print("Searching: %s files" % len(files))
print("Gathering image information")
images = []

#h_tmp, tmp_path = tempfile.mkstemp("ddb")
#os.close(h_tmp)
#ddb("info", "--format", "json", "-o", tmp_path, *files)
#images = []
#with open(tmp_path) as f:
#    images = json.loads(f.read())

# TODO: ddb cannot handle FLIR tags, yet...
img_min_t = np.Inf
img_max_t = -np.Inf
out = exiftool(*files, "-s", "-s", "-s", "-DateTimeOriginal")
lines = [l.strip() for l in out.split("\n")]

# Handle case with single file
if len(files) == 1:
    lines.insert(0, "======== %s" % files[0])
    lines.append("")

lines = lines[:-2]
it = iter(lines)
for line in it:
    if "========" in line:
        file = line.replace("======== ", "")
        dto = next(it)

        # Make strptime happy
        if dto[-6] == "+" and dto[-3] == ":":
            dto = dto[:-6] + dto[-6:].replace(":", "")

        date = datetime.datetime.strptime(dto, '%Y:%m:%d %H:%M:%S.%f%z')
        utctime = date.timestamp()

        images.append({
            'path': file,
            'utctime': utctime
        })

        img_min_t = min(img_min_t, utctime)
        img_max_t = max(img_max_t, utctime)

if len(images) == 0:
    die("No images")

print("Found %s images" % len(images))

if len(images) != len(files):
    print("WARNING: some files could not be parsed")

print("Reading trajectory file")
trajectories = [[], [], []]
times = []
# gps_times = []

with open(args.trajectory) as csvfile:
    reader = csv.DictReader(csvfile)
    i = 0
    for row in reader:
        gps_time = float(row['Time[s]']) + 1e9 # Adjusted GPS time
        easting = float(row['Easting[m]'])
        northing = float(row['Northing[m]'])
        height = float(row['Height[m]'])

        utctime = tconvert(gps_time).timestamp()
        
        # gps_times.append(gps_time)
        times.append(utctime)

        trajectories[0].append(easting)
        trajectories[1].append(northing)
        trajectories[2].append(height)
        
        if i % 1000 == 0:
            print(".", end ="", flush=True)
        i += 1
    print("")

traj_min_t = np.min(times)
traj_max_t = np.max(times)

# print(np.min(gps_times))
# print(np.max(gps_times))

# Quick check on interpolation values...
print("Images time range: %s" % [img_min_t, img_max_t])
print("Trajectories time range: %s" % [traj_min_t, traj_max_t])

if img_min_t < traj_min_t:
    die("Image min range < Trajectories min range. The images timestamps fall outside of the available times in the trajectory file.")

if img_max_t > traj_max_t:
    die("Image max range > Trajectories max range. The images timestamps fall outside of the available times in the trajectory file.")

print("Interpolating GPS positions")
interpolator = interp1d(times, trajectories, kind=args.interpolation)
for img in images:
    print("%s --> %s" % (img['path'], interpolator(img['utctime'])))
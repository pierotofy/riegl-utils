import argparse
import subprocess
import os
import glob
import tempfile
import datetime
import json
import shutil
import csv
from gwpy.time import tconvert
from PIL import Image
import piexif

parser = argparse.ArgumentParser(description='Trajectory to GPS')
parser.add_argument('--crs', '-c',
                    metavar='EPSG:xxxx',
                    required=True,
                    help='EPSG code of trajectory values')
parser.add_argument('--input', '-i',
                    metavar='<path>',
                    required=True,
                    help='Path of images to augment with trajectory')
parser.add_argument('--trajectory', '-t',
                    metavar='<path>',
                    required=True,
                    help='Path of trajectory file')
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
    print(msg)
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

print("Gathering image information")
images = []


#h_tmp, tmp_path = tempfile.mkstemp("ddb")
#os.close(h_tmp)
#ddb("info", "--format", "json", "-o", tmp_path, *files)
#images = []
#with open(tmp_path) as f:
#    images = json.loads(f.read())

# TODO: ddb cannot handle FLIR tags, yet...
out = exiftool(*files, "-s", "-s", "-s", "-DateTimeOriginal")
lines = [l.strip() for l in out.split("\n")]
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
        images.append({
            'path': file,
            'utctime': date.timestamp()
        })

if len(images) == 0:
    die("No images")

print("Found %s images" % len(images))

if len(images) != len(files):
    print("WARNING: some files could not be parsed")

print("Reading trajectory file")
trajectories = []
with open(args.trajectory) as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        time = float(row['Time[s]']) + 1e9 # Adjusted GPS time
        easting = float(row['Easting[m]'])
        northing = float(row['Northing[m]'])
        height = float(row['Height[m]'])
        utctime = tconvert(time).timestamp()

        trajectories.append([utctime, easting, northing, height])


#! /usr/bin/python3

import os
import sys
import subprocess
import shutil
import datetime

QUIET = False

COMPOSITIONS = [
    "CopyOpacity",
]

def log(message):
    global QUIET
    if not QUIET:
        print(message)

if len(sys.argv) >= 6:
    QUIET = True

if len(sys.argv) < 2:
    print("An input PDF file is required, like Sample.pdf")
    sys.exit(1)

if len(sys.argv) < 3:
    print("An output directory is required, example ~/Desktop/extracted")
    sys.exit(1)

if len(sys.argv) < 4 or sys.argv[3] == "all":
    log("Will only attempt CopyOpacity composition")
else:
    log(f'Will attempt [{sys.argv[3]}] compositions')
    COMPOSITIONS = sys.argv[3].split(',')

SAMPLE_IMAGE_NUM = 1
if len(sys.argv) >= 5:
    log(f'Will copy samples using image [{sys.argv[4]}]')
    SAMPLE_IMAGE_NUM = int(sys.argv[4])

INPUT_PDF_FILE = sys.argv[1]
OUTPUT_DIR = sys.argv[2]

# Function to create a unique directory name if OUTPUT_DIR exists
def create_unique_directory(base_dir):
    # If the directory doesn't exist, use it as is
    if not os.path.exists(base_dir):
        return base_dir
    # Otherwise, append a timestamp to create a unique directory name
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    new_dir = f"{base_dir}_{timestamp}"
    print(f"The specified output directory exists. Using a unique directory instead: {new_dir}")
    return new_dir

# Use the function to ensure the OUTPUT_DIR is unique
OUTPUT_DIR = create_unique_directory(OUTPUT_DIR)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def execute(command):
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    result = process.returncode
    if result != 0:
        print("An error occurred while running {}".format(command))
        print("stdout: {}".format(stdout))
        print("stderr: {}".format(stderr))
        sys.exit(1)
    return {
        "result": result,
        "stdout": stdout.decode('utf-8').split('\n'),
        "stderr": stderr.decode('utf-8').split('\n')
    }

EXTRACT_DIR = os.path.join(OUTPUT_DIR, "10-extract")
os.makedirs(EXTRACT_DIR, exist_ok=True)

log(f"Extract image data from PDF to [{EXTRACT_DIR}]")
command = f'pdfimages -png "{INPUT_PDF_FILE}" "{EXTRACT_DIR}/image"'
execute(command)

log("Gather extracted image paths")
extracted_images = {}
for root, dirs, files in os.walk(EXTRACT_DIR):
    for file in files:
        image_num = int(file.split('-')[1].split('.')[0])
        extracted_images[image_num] = os.path.join(root, file)

class PdfImageMetadata:
    def __init__(self, text):
        parts = text.split()
        self.page = self.num = self.type = self.width = self.height = self.color = None
        self.comp = self.bpc = self.enc = self.interop = self.object = self.id = None
        self.x_ppi = self.y_ppi = self.size = self.ratio = None

        metadata_keys = ['page', 'num', 'type', 'width', 'height', 'color',
                         'comp', 'bpc', 'enc', 'interop', 'object', 'id',
                         'x_ppi', 'y_ppi', 'size', 'ratio']
        for i, key in enumerate(metadata_keys):
            if i < len(parts):
                setattr(self, key, parts[i])

        self.num = int(self.num) if self.num and self.num.isdigit() else 0
        self.object = int(self.object) if self.object and self.object.isdigit() else 0

pdf_objects = {}
log("Parse PDF image metadata")
command = f'pdfimages -list "{INPUT_PDF_FILE}"'
list_results = execute(command)
count = 0
for line in list_results['stdout']:
    count += 1
    if count < 3:  # Skipping header lines
        continue
    image = PdfImageMetadata(line)
    if image.type and ('image' in image.type or 'smask' in image.type):
        if image.object not in pdf_objects:
            pdf_objects[image.object] = {}
        pdf_objects[image.object][image.type] = image

MASKED_DIR = os.path.join(OUTPUT_DIR, '30-masked')
SAMPLE_DIR = os.path.join(OUTPUT_DIR, '25-samples')
ORGANIZE_DIR = os.path.join(OUTPUT_DIR, '15-organized')
RAW_MASK_DIR = os.path.join(ORGANIZE_DIR, 'mask')
RAW_IMAGE_DIR = os.path.join(ORGANIZE_DIR, 'image')
for dir_path in [MASKED_DIR, SAMPLE_DIR, ORGANIZE_DIR, RAW_MASK_DIR, RAW_IMAGE_DIR]:
    os.makedirs(dir_path, exist_ok=True)

def compose(image, mask, destination, mode, prefix):
    merged_dir = os.path.join(MASKED_DIR, prefix, mode)
    os.makedirs(merged_dir, exist_ok=True)
    merged_file = f'{destination:05d}.png'
    merged_path = os.path.join(merged_dir, merged_file)
    command = f'convert "{image}" "{mask}" -compose {mode} -composite "{merged_path}"'
    execute(command)
    if destination == SAMPLE_IMAGE_NUM:
        sample_path = os.path.join(SAMPLE_DIR, f'{prefix}-{mode}-{destination:05d}.png')
        shutil.copy(merged_path, sample_path)

log("Merging masked images, copying standalone images")
merged_count = 0
images_counted = False
for mode in COMPOSITIONS:
    log(f"Compose images using mode [{mode}]")
    for k, v in pdf_objects.items():
        if 'smask' in v and 'image' in v:
            image = extracted_images[v['image'].num]
            mask = extracted_images[v['smask'].num]
            shutil.copy(image, os.path.join(RAW_IMAGE_DIR, f"{v['image'].num}.png"))
            shutil.copy(mask, os.path.join(RAW_MASK_DIR, f"{v['smask'].num}.png"))
            compose(image, mask, v['image'].num, mode, "image+mask")
            if not images_counted:
                merged_count += 1
        elif 'image' in v:
            source = extracted_images[v['image'].num]
            shutil.copy(source, os.path.join(RAW_IMAGE_DIR, f"{v['image'].num}.png"))
    images_counted = True

log(f"Raw images sorted in [{ORGANIZE_DIR}]")
log(f"{merged_count} masked images merged in [{len(COMPOSITIONS)}] ways to [{MASKED_DIR}]")

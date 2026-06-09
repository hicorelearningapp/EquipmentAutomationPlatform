import os
import shutil
import re

def organize_images(source_dir):
    """Organize Rajini images into year and movie hierarchies.

    Args:
        source_dir (str): Path to the directory containing the original images.
    """
    pattern = re.compile(r'^(?P<year>\d{4})_(?P<movie>.+?)_(poster|still(?:_\d+)?)\.jpg$', re.IGNORECASE)
    for fname in os.listdir(source_dir):
        if not fname.lower().endswith('.jpg'):
            continue
        match = pattern.match(fname)
        if not match:
            print(f"Skipping unrecognized file: {fname}")
            continue
        year = match.group('year')
        movie = match.group('movie')
        # Target directories
        year_dir = os.path.join(source_dir, year)
        movie_dir = os.path.join(year_dir, movie)   # nested inside the year folder
        os.makedirs(year_dir, exist_ok=True)
        os.makedirs(movie_dir, exist_ok=True)
        src_path = os.path.join(source_dir, fname)
        # Move file into nested year/movie hierarchy
        dst_path = os.path.join(movie_dir, fname)
        shutil.move(src_path, dst_path)
        print(f"Processed {fname}: year={year}, movie={movie}")

if __name__ == "__main__":
    # Adjust this path if the script is placed elsewhere.
    source_dir = r"e:\\Github\\EquipmentAutomationPlatforms\\rajini_images"
    organize_images(source_dir)

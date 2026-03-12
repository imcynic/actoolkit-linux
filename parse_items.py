#!/usr/bin/env python3
"""
Parser for items.pas from AC Toolkit (Animal Crossing: City Folk save editor).
Reads the Delphi source and generates items_db.py with all item data.
"""

import re

INPUT_FILE = "/home/bryan/actoolkit/items.pas"
OUTPUT_FILE = "/home/bryan/actoolkit-linux/items_db.py"

# Category mappings based on the variable name prefixes
CATEGORY_MAP = {
    # Acres
    "a_barrier": ("acres", "barrier"),
    "a_normal": ("acres", "normal"),
    "a_ocean": ("acres", "ocean"),
    "a_river": ("acres", "river"),
    "a_transition": ("acres", "transition"),
    # Terrain
    "t_flowers": ("terrain", "flowers"),
    "t_flowers2": ("terrain", "flowers2"),
    "t_misc": ("terrain", "misc"),
    "t_patterns": ("terrain", "patterns"),
    "t_rocks": ("terrain", "rocks"),
    "t_trees": ("terrain", "trees"),
    "t_turnips": ("terrain", "turnips"),
    "t_weeds": ("terrain", "weeds"),
    # Items
    "i_bells": ("items", "bells"),
    "i_insects": ("items", "insects"),
    "i_fish": ("items", "fish"),
    "i_flooring": ("items", "flooring"),
    "i_flowers": ("items", "flowers"),
    "i_flowerbags": ("items", "flowerbags"),
    "i_fruits": ("items", "fruits"),
    "i_glasses": ("items", "glasses"),
    "i_hats": ("items", "hats"),
    "i_songs": ("items", "songs"),
    "i_mushrooms": ("items", "mushrooms"),
    "i_paper": ("items", "paper"),
    "i_seashells": ("items", "seashells"),
    "i_shirts": ("items", "shirts"),
    "i_umbrellas": ("items", "umbrellas"),
    "i_wallpaper": ("items", "wallpaper"),
    # Furniture
    "i_equipment": ("furniture", "equipment"),
    "i_dlc": ("furniture", "dlc"),
    "i_series": ("furniture", "series"),
    "i_boxing": ("furniture", "boxing"),
    "i_classroom": ("furniture", "classroom"),
    "i_construction": ("furniture", "construction"),
    "i_lab": ("furniture", "lab"),
    "i_mario": ("furniture", "mario"),
    "i_garden": ("furniture", "garden"),
    "i_nursery": ("furniture", "nursery"),
    "i_ship": ("furniture", "ship"),
    "i_space": ("furniture", "space"),
    "i_western": ("furniture", "western"),
    # Other
    "i_other1": ("other", "other1"),
    "i_other2": ("other", "other2"),
    "i_other3": ("other", "other3"),
    "i_nintendo": ("other", "nintendo"),
    "i_gyroids": ("other", "gyroids"),
    "i_fossils": ("other", "fossils"),
    "i_paintings": ("other", "paintings"),
    "i_plants": ("other", "plants"),
    "i_notused": ("other", "notused"),
}


def parse_delphi_string(s):
    """Parse a Delphi string literal, handling '' escape for single quotes."""
    return s.replace("''", "'")


def parse_items_pas(filename):
    """Parse the items.pas file and return a dict of arrays with their items."""
    with open(filename, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    # Strip Delphi // comments from each line before joining
    cleaned_lines = []
    for line in lines:
        # Find // that's not inside a string
        in_string = False
        i = 0
        result = line
        while i < len(line) - 1:
            if line[i] == "'":
                in_string = not in_string
            elif not in_string and line[i] == '/' and line[i+1] == '/':
                result = line[:i] + '\n'
                break
            i += 1
        cleaned_lines.append(result)

    content = ''.join(cleaned_lines)

    # Find all array declarations
    # Pattern: varname: array[0..N] of TItem = ( ... );
    array_pattern = re.compile(
        r'(\w+)\s*:\s*array\[.*?\]\s*of\s*TItem\s*=\s*\((.*?)\)\s*;',
        re.DOTALL
    )

    # Pattern for individual item entries
    # (code: $XXXX; NameEA: '...'; NameSA: '...'; NameFC: '...'; NameEU: '...'; NameGE: '...'; NameIT: '...'; NameSE: '...'; NameFE: '...'; NameJA: '...';)
    item_pattern = re.compile(
        r'\(code:\s*\$([0-9A-Fa-f]+)\s*;\s*'
        r"NameEA:\s*'((?:[^']|'')*)'\s*;\s*"
        r"NameSA:\s*'((?:[^']|'')*)'\s*;\s*"
        r"NameFC:\s*'((?:[^']|'')*)'\s*;\s*"
        r"NameEU:\s*'((?:[^']|'')*)'\s*;\s*"
        r"NameGE:\s*'((?:[^']|'')*)'\s*;\s*"
        r"NameIT:\s*'((?:[^']|'')*)'\s*;\s*"
        r"NameSE:\s*'((?:[^']|'')*)'\s*;\s*"
        r"NameFE:\s*'((?:[^']|'')*)'\s*;\s*"
        r"NameJA:\s*'((?:[^']|'')*)'\s*;\s*\)"
    )

    arrays = {}
    total_items = 0

    for match in array_pattern.finditer(content):
        array_name = match.group(1)
        array_body = match.group(2)

        items = []
        for item_match in item_pattern.finditer(array_body):
            code = int(item_match.group(1), 16)
            name_ea = parse_delphi_string(item_match.group(2))
            name_sa = parse_delphi_string(item_match.group(3))
            name_fc = parse_delphi_string(item_match.group(4))
            name_eu = parse_delphi_string(item_match.group(5))
            name_ge = parse_delphi_string(item_match.group(6))
            name_it = parse_delphi_string(item_match.group(7))
            name_se = parse_delphi_string(item_match.group(8))
            name_fe = parse_delphi_string(item_match.group(9))
            name_ja = parse_delphi_string(item_match.group(10))

            items.append({
                "code": code,
                "name_ea": name_ea,
                "name_sa": name_sa,
                "name_fc": name_fc,
                "name_eu": name_eu,
                "name_ge": name_ge,
                "name_it": name_it,
                "name_se": name_se,
                "name_fe": name_fe,
                "name_ja": name_ja,
            })

        arrays[array_name] = items
        total_items += len(items)
        print(f"  Parsed {array_name}: {len(items)} items")

    print(f"\nTotal arrays: {len(arrays)}")
    print(f"Total items: {total_items}")
    return arrays


def escape_python_string(s):
    """Escape a string for use in Python source code with double quotes."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def generate_python(arrays, output_file):
    """Generate the items_db.py file."""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write('# Auto-generated from items.pas - ACCF Item Database\n')
        f.write('# Animal Crossing: City Folk (ACCF) complete item database\n')
        f.write('# Categories: terrain/acre items use only NameEA, holdable/furniture items have all 9 languages\n')
        f.write('#\n')
        f.write('# Language codes:\n')
        f.write('#   name_ea = English (Americas)\n')
        f.write('#   name_sa = Spanish (Americas)\n')
        f.write('#   name_fc = French (Canada)\n')
        f.write('#   name_eu = English (Europe)\n')
        f.write('#   name_ge = German\n')
        f.write('#   name_it = Italian\n')
        f.write('#   name_se = Spanish (Europe)\n')
        f.write('#   name_fe = French (Europe)\n')
        f.write('#   name_ja = Japanese\n')
        f.write('\n')

        # Write ITEMS dict
        f.write('ITEMS = {\n')

        # Track all items for CATEGORIES
        categories_data = {}

        # Hardcoded special items from global.pas
        hardcoded = [
            (0xFFF1, "Empty", "special", "hardcoded"),
            (0xD000, "Sign", "special", "hardcoded"),
            (0x7003, "Bus Stop", "special", "hardcoded"),
            (0xF030, "Used Space", "special", "hardcoded"),
            (0x7000, "Snowman 1", "special", "hardcoded"),
            (0x7001, "Snowman 2", "special", "hardcoded"),
            (0x7002, "Snowman 3", "special", "hardcoded"),
        ]

        cat_key = "special_hardcoded"
        categories_data[cat_key] = []

        for code, name, category, subcategory in hardcoded:
            categories_data[cat_key].append(code)
            ea = escape_python_string(name)
            f.write(f'    0x{code:04X}: {{\n')
            f.write(f'        "name_ea": "{ea}",\n')
            f.write(f'        "name_sa": "{ea}",\n')
            f.write(f'        "name_fc": "{ea}",\n')
            f.write(f'        "name_eu": "{ea}",\n')
            f.write(f'        "name_ge": "{ea}",\n')
            f.write(f'        "name_it": "{ea}",\n')
            f.write(f'        "name_se": "{ea}",\n')
            f.write(f'        "name_fe": "{ea}",\n')
            f.write(f'        "name_ja": "{ea}",\n')
            f.write(f'        "category": "{category}",\n')
            f.write(f'        "subcategory": "{subcategory}",\n')
            f.write('    },\n')

        # Process all arrays in order
        # Sort by category map order (maintain original file order as much as possible)
        ordered_keys = list(CATEGORY_MAP.keys())

        for array_name in ordered_keys:
            if array_name not in arrays:
                print(f"  WARNING: {array_name} not found in parsed data!")
                continue

            category, subcategory = CATEGORY_MAP[array_name]
            items = arrays[array_name]
            cat_key = f"{array_name}"
            categories_data[cat_key] = []

            f.write(f'\n    # === {array_name} ({category}/{subcategory}) - {len(items)} items ===\n')

            for item in items:
                code = item["code"]
                categories_data[cat_key].append(code)

                ea = escape_python_string(item["name_ea"])
                sa = escape_python_string(item["name_sa"])
                fc = escape_python_string(item["name_fc"])
                eu = escape_python_string(item["name_eu"])
                ge = escape_python_string(item["name_ge"])
                it = escape_python_string(item["name_it"])
                se = escape_python_string(item["name_se"])
                fe = escape_python_string(item["name_fe"])
                ja = escape_python_string(item["name_ja"])

                # For terrain/acre items with empty language fields, copy NameEA
                if not sa and not eu and not ge:
                    sa = ea
                    fc = ea
                    eu = ea
                    ge = ea
                    it = ea
                    se = ea
                    fe = ea
                    ja = ea

                f.write(f'    0x{code:04X}: {{\n')
                f.write(f'        "name_ea": "{ea}",\n')
                f.write(f'        "name_sa": "{sa}",\n')
                f.write(f'        "name_fc": "{fc}",\n')
                f.write(f'        "name_eu": "{eu}",\n')
                f.write(f'        "name_ge": "{ge}",\n')
                f.write(f'        "name_it": "{it}",\n')
                f.write(f'        "name_se": "{se}",\n')
                f.write(f'        "name_fe": "{fe}",\n')
                f.write(f'        "name_ja": "{ja}",\n')
                f.write(f'        "category": "{category}",\n')
                f.write(f'        "subcategory": "{subcategory}",\n')
                f.write('    },\n')

        # Also handle any arrays not in CATEGORY_MAP (in case we missed some)
        for array_name in arrays:
            if array_name not in CATEGORY_MAP:
                print(f"  WARNING: Unknown array '{array_name}' - adding as uncategorized")
                items = arrays[array_name]
                cat_key = array_name
                categories_data[cat_key] = []

                f.write(f'\n    # === {array_name} (uncategorized) - {len(items)} items ===\n')

                for item in items:
                    code = item["code"]
                    categories_data[cat_key].append(code)

                    ea = escape_python_string(item["name_ea"])
                    sa = escape_python_string(item["name_sa"])
                    fc = escape_python_string(item["name_fc"])
                    eu = escape_python_string(item["name_eu"])
                    ge = escape_python_string(item["name_ge"])
                    it = escape_python_string(item["name_it"])
                    se = escape_python_string(item["name_se"])
                    fe = escape_python_string(item["name_fe"])
                    ja = escape_python_string(item["name_ja"])

                    if not sa and not eu and not ge:
                        sa = ea
                        fc = ea
                        eu = ea
                        ge = ea
                        it = ea
                        se = ea
                        fe = ea
                        ja = ea

                    f.write(f'    0x{code:04X}: {{\n')
                    f.write(f'        "name_ea": "{ea}",\n')
                    f.write(f'        "name_sa": "{sa}",\n')
                    f.write(f'        "name_fc": "{fc}",\n')
                    f.write(f'        "name_eu": "{eu}",\n')
                    f.write(f'        "name_ge": "{ge}",\n')
                    f.write(f'        "name_it": "{it}",\n')
                    f.write(f'        "name_se": "{se}",\n')
                    f.write(f'        "name_fe": "{fe}",\n')
                    f.write(f'        "name_ja": "{ja}",\n')
                    f.write('        "category": "uncategorized",\n')
                    f.write(f'        "subcategory": "{array_name}",\n')
                    f.write('    },\n')

        f.write('}\n\n\n')

        # Write CATEGORIES dict
        f.write('CATEGORIES = {\n')

        # Special hardcoded
        f.write('    "special_hardcoded": [\n')
        for code in categories_data.get("special_hardcoded", []):
            f.write(f'        0x{code:04X},\n')
        f.write('    ],\n')

        # Acres
        f.write('\n    # Acres\n')
        for array_name in ordered_keys:
            if not array_name.startswith("a_"):
                continue
            if array_name not in categories_data:
                continue
            f.write(f'    "{array_name}": [\n')
            for code in categories_data[array_name]:
                f.write(f'        0x{code:04X},\n')
            f.write('    ],\n')

        # Terrain
        f.write('\n    # Terrain\n')
        for array_name in ordered_keys:
            if not array_name.startswith("t_"):
                continue
            if array_name not in categories_data:
                continue
            f.write(f'    "{array_name}": [\n')
            for code in categories_data[array_name]:
                f.write(f'        0x{code:04X},\n')
            f.write('    ],\n')

        # Items (i_ prefix but not furniture)
        item_arrays = ["i_bells", "i_insects", "i_fish", "i_flooring", "i_flowers",
                       "i_flowerbags", "i_fruits", "i_glasses", "i_hats", "i_songs",
                       "i_mushrooms", "i_paper", "i_seashells", "i_shirts", "i_umbrellas",
                       "i_wallpaper"]
        f.write('\n    # Items\n')
        for array_name in item_arrays:
            if array_name not in categories_data:
                continue
            f.write(f'    "{array_name}": [\n')
            for code in categories_data[array_name]:
                f.write(f'        0x{code:04X},\n')
            f.write('    ],\n')

        # Furniture
        furniture_arrays = ["i_equipment", "i_dlc", "i_series", "i_boxing", "i_classroom",
                           "i_construction", "i_lab", "i_mario", "i_garden", "i_nursery",
                           "i_ship", "i_space", "i_western"]
        f.write('\n    # Furniture\n')
        for array_name in furniture_arrays:
            if array_name not in categories_data:
                continue
            f.write(f'    "{array_name}": [\n')
            for code in categories_data[array_name]:
                f.write(f'        0x{code:04X},\n')
            f.write('    ],\n')

        # Other
        other_arrays = ["i_other1", "i_other2", "i_other3", "i_nintendo", "i_gyroids",
                        "i_fossils", "i_paintings", "i_plants", "i_notused"]
        f.write('\n    # Other\n')
        for array_name in other_arrays:
            if array_name not in categories_data:
                continue
            f.write(f'    "{array_name}": [\n')
            for code in categories_data[array_name]:
                f.write(f'        0x{code:04X},\n')
            f.write('    ],\n')

        # Any uncategorized
        for cat_key in categories_data:
            if cat_key not in ordered_keys and cat_key != "special_hardcoded":
                f.write('\n    # Uncategorized\n')
                f.write(f'    "{cat_key}": [\n')
                for code in categories_data[cat_key]:
                    f.write(f'        0x{code:04X},\n')
                f.write('    ],\n')

        f.write('}\n')

    print(f"\nGenerated {output_file}")


def main():
    print("Parsing items.pas...")
    arrays = parse_items_pas(INPUT_FILE)
    print("\nGenerating items_db.py...")
    generate_python(arrays, OUTPUT_FILE)

    # Verification
    print("\n--- Verification ---")
    total = 7  # hardcoded items
    for name, items in arrays.items():
        total += len(items)
    print(f"Total items (including 7 hardcoded): {total}")


if __name__ == "__main__":
    main()

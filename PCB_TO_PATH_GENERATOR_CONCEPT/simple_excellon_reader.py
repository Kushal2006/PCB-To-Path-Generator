import sys

# ---------------------------------------------------------------
# DEFAULT SETTINGS -- you can just edit these two lines instead of
# typing filenames on the command line, if you prefer.
# ---------------------------------------------------------------
INPUT_FILE = "test-PTH.drl"
OUTPUT_FILE = "holes.csv"


def main():
    input_file = INPUT_FILE
    output_file = OUTPUT_FILE

    # allow overriding the defaults from the command line
    if len(sys.argv) >= 2:
        input_file = sys.argv[1]
    if len(sys.argv) >= 3:
        output_file = sys.argv[2]

    lines = read_all_lines(input_file)

    # These describe HOW the numbers in the file are written.
    # They get updated as we read the header of the file.
    units = "metric"              # "metric" or "inch"
    zero_suppression = "leading"  # "leading" or "trailing"

    tool_sizes = {}   # example: {"T01": 0.7, "T02": 1.0}
    holes = []        # example: [{"tool": "T01", "diameter_mm": 0.7, "x_mm": 12.5, "y_mm": 7.5}, ...]

    reading_header = True   # True while we are still in the header section
    current_tool = None     # which tool is currently selected, e.g. "T01"

    for raw_line in lines:
        line = raw_line.strip()   # remove spaces/newline from both ends

        # skip blank lines and comment lines
        if line == "" or line.startswith(";"):
            continue

        # "%" marks the end of the header section
        if line == "%":
            reading_header = False
            continue

        # "M48" marks the start of the header section
        if line.upper() == "M48":
            reading_header = True
            continue

        # "M30" marks the end of the whole file -- stop reading
        if line.upper().startswith("M30"):
            break

        # ---------------- HEADER LINES ----------------
        if reading_header:
            if "METRIC" in line.upper():
                units = "metric"
            if "INCH" in line.upper():
                units = "inch"
            if "LZ" in line.upper():
                zero_suppression = "leading"
            if "TZ" in line.upper():
                zero_suppression = "trailing"

            # A tool definition line looks like "T1C0.700"
            # meaning: Tool 1 has a diameter of 0.700
            if line.upper().startswith("T") and "C" in line.upper():
                tool_name, diameter_raw = read_tool_definition(line)
                if diameter_raw is not None:
                    diameter_mm = diameter_raw
                    if units == "inch":
                        diameter_mm = diameter_raw * 25.4
                    tool_sizes[tool_name] = diameter_mm

            continue   # done handling this header line, go to next line

        # ---------------- BODY LINES ----------------

        # A tool-selection line looks like "T1" all by itself (no X or Y)
        if line.upper().startswith("T") and "X" not in line.upper() and "Y" not in line.upper():
            current_tool = clean_tool_name(line)
            continue

        # A coordinate line looks like "X12500Y7500" or "X10.500Y-20.750"
        if "X" in line.upper() or "Y" in line.upper():
            x_text, y_text = split_x_and_y(line)
            x_mm = text_to_millimeters(x_text, units, zero_suppression)
            y_mm = text_to_millimeters(y_text, units, zero_suppression)

            diameter_mm = tool_sizes.get(current_tool, 0.0)

            hole = {
                "tool": current_tool,
                "diameter_mm": round(diameter_mm, 4),
                "x_mm": round(x_mm, 4),
                "y_mm": round(y_mm, 4),
            }
            holes.append(hole)

    write_csv(holes, output_file)

    print("Units detected:", units)
    print("Zero suppression detected:", zero_suppression)
    print("Tools found:", tool_sizes)
    print("Number of holes found:", len(holes))
    print("Saved results to:", output_file)


# =================================================================
# HELPER FUNCTIONS
# Each one does ONE small job. This makes the code easier to read
# and easier to test/fix piece by piece.
# =================================================================

def read_all_lines(filepath):
    """Open a file and return a list of all its lines."""
    with open(filepath, "r") as f:
        return f.readlines()


def read_tool_definition(line):
    """
    Turns a line like 'T1C0.700' into ('T01', 0.700).
    The letter C separates the tool number from its diameter.
    """
    upper_line = line.upper()
    parts = upper_line.split("C")

    if len(parts) != 2:
        return None, None   # this line didn't look like a tool definition

    tool_name = clean_tool_name(parts[0])

    try:
        diameter = float(parts[1])
    except ValueError:
        return tool_name, None

    return tool_name, diameter


def clean_tool_name(text):
    """
    Makes tool names consistent, e.g. 'T1' and 'T01' both become 'T01'.
    """
    digits_only = ""
    for character in text:
        if character.isdigit():
            digits_only += character

    tool_number = int(digits_only)
    return "T" + str(tool_number).zfill(2)   # zfill(2) pads with a leading zero if needed


def split_x_and_y(line):
    """
    Splits a line like 'X12500Y7500' into two separate text pieces:
    x_text = '12500' and y_text = '7500'
    """
    x_text = ""
    y_text = ""

    currently_reading = None   # will be set to "x" or "y"

    for character in line:
        upper_character = character.upper()

        if upper_character == "X":
            currently_reading = "x"
            continue
        if upper_character == "Y":
            currently_reading = "y"
            continue

        if currently_reading == "x":
            x_text += character
        elif currently_reading == "y":
            y_text += character

    return x_text, y_text


def text_to_millimeters(text, units, zero_suppression):
    """
    Converts a raw coordinate piece of text (like '12500' or '10.500')
    into an actual number in millimeters.
    """
    if text == "":
        return 0.0

    # handle negative numbers
    is_negative = False
    if text.startswith("-"):
        is_negative = True
        text = text[1:]
    if text.startswith("+"):
        text = text[1:]

    if "." in text:
        # EASY CASE: the file already tells us exactly where the decimal
        # point goes, so we can just trust it directly.
        value = float(text)

    else:
        # HARDER CASE: there is no decimal point in the text, so we have
        # to guess where it goes, based on the file's declared format.
        # Most files use 3 digits before the decimal point and
        # 3 digits after it (called a "3.3 format").
        digits_before_decimal = 3
        digits_after_decimal = 3
        total_digits_needed = digits_before_decimal + digits_after_decimal

        if zero_suppression == "leading":
            # pad missing zeros onto the FRONT of the number
            text = text.rjust(total_digits_needed, "0")
        else:
            # pad missing zeros onto the END of the number
            text = text.ljust(total_digits_needed, "0")

        whole_part = text[:digits_before_decimal]
        fraction_part = text[digits_before_decimal:]
        value = float(whole_part + "." + fraction_part)

    if units == "inch":
        value = value * 25.4   # convert inches to millimeters

    if is_negative:
        value = -value

    return value


def write_csv(holes, filepath):
    """Writes the list of holes out to a simple CSV file."""
    with open(filepath, "w") as f:
        f.write("tool,diameter_mm,x_mm,y_mm\n")
        for hole in holes:
            line = f"{hole['tool']},{hole['diameter_mm']},{hole['x_mm']},{hole['y_mm']}\n"
            f.write(line)


# This makes sure main() only runs when you execute this file directly,
# not if it gets imported by another program.
if __name__ == "__main__":
    main()

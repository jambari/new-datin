import sys

# --- Configuration ---
input_filename = 'holtekamp.xyz'  # 👈 Change this to your input file name
output_filename = 'holtekamp_baru.xyz' # 👈 This will be the new file created
min_elev = 5.0
max_elev = 30.0
replacement_value = 4.0
# ---------------------

print(f"⚙️ Processing file: {input_filename}")

try:
    # Use 'with' to ensure files are properly closed
    with open(input_filename, 'r') as infile, open(output_filename, 'w') as outfile:
        # Read the file line by line
        for i, line in enumerate(infile):
            try:
                # Split the line into X, Y, and Z parts
                parts = line.strip().split()
                
                # Ensure the line has at least 3 columns (X, Y, Z)
                if len(parts) >= 3:
                    x, y = parts[0], parts[1]
                    elevation = float(parts[2])

                    # Check if the elevation is within the target range
                    if min_elev <= elevation <= max_elev:
                        # If it is, replace it with the new value
                        new_line = f"{x} {y} {replacement_value}\n"
                    else:
                        # Otherwise, keep the original line
                        new_line = line
                    
                    outfile.write(new_line)
                else:
                    # If the line doesn't have 3 parts, write it as is
                    outfile.write(line)

            except (ValueError, IndexError):
                # This handles cases where a line is not formatted correctly (e.g., text headers)
                print(f"⚠️ Skipping malformed line {i+1}: {line.strip()}")
                outfile.write(line) # Write the problematic line to the new file as is

    print(f"✅ Success! Processed data has been saved to: {output_filename}")

except FileNotFoundError:
    print(f"❌ ERROR: The file '{input_filename}' was not found. Please check the file name and path.")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
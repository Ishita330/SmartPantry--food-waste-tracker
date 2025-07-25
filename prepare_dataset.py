import pandas as pd

# Step 1: Load a small chunk of the large dataset
df = pd.read_csv('recipes_data.csv', usecols=['title', 'NER'], nrows=500, on_bad_lines='skip')

# Step 2: Drop rows that are missing either title or ingredients
df.dropna(subset=['title', 'NER'], inplace=True)

# Step 3: Clean the 'NER' ingredients column
df['NER'] = df['NER'].str.lower().str.replace(r'[\[\]\'"]', '', regex=True)

# Step 4: Rename columns to match what your app expects
df.rename(columns={'title': 'name', 'NER': 'ingredients'}, inplace=True)

# Step 5: Save to a smaller file
df.to_csv('recipes_sample.csv', index=False)

print("✅ Sample dataset created: recipes_sample.csv (✓ Ready to use)")

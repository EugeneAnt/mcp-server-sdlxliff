# Claude Cowork Workflow Example

This document shows the recommended workflow for reviewing and updating SDLXLIFF translations using Claude Cowork.

## Setup

1. Open Claude Desktop
2. Enter Cowork mode
3. Add your directory containing SDLXLIFF files (e.g., `/Users/yevgeniyantonov/PycharmProjects/CCDesktopXliffTool/sample`)

## Step 1: Read and Review

Simply ask Claude:

```
Read the xliff file and check the translation
```

Or with specific instructions:

```
Read the xliff file and review the Russian translations for:
- Grammar errors
- Terminology consistency
- Cultural appropriateness
- Completeness
```

### What Happens:
- Claude uses `find_sdlxliff_files` to discover files in the directory
- Claude uses `read_sdlxliff` to extract all segments
- Claude analyzes each segment and identifies issues

### Example Response:
```
I found 1 SDLXLIFF file: russian_sample.sdlxliff

After reviewing the 27 segments, I found these issues:

1. Segment c63ce93e-bb51-49f6-993b-0697205bbede
   - Source: "Smart Switch seamlessly transfers..."
   - Current: "Приложение Smart Switch позволяет без проблем..."
   - Issue: "без проблем" is too informal, should be "беспрепятственно"

2. Segment 045c01df-5072-4628-a5c3-da47ab4b38b6
   - Source: "Can I still make video calls..."
   - Current: "Могу ли я по-прежнему звонить по видео..."
   - Issue: "звонить по видео" is awkward, should use "совершать видеозвонки"

Would you like me to update these translations?
```

## Step 2: Apply Corrections

After reviewing Claude's findings, ask:

```
Update the translations with your corrections and set status to needs-translation
```

Or be more specific:

```
Apply all the corrections you suggested and mark each updated segment as needs-translation
```

### What Happens:
- For each problematic segment, Claude uses:
  - `update_sdlxliff_segment` with the corrected text and status "needs-translation"
  - OR `reject_sdlxliff_segment` with corrected text and status
- Claude uses `save_sdlxliff` to write changes back to the file

### Example Response:
```
I've updated the following segments and marked them as needs-translation:

✓ Segment c63ce93e-bb51-49f6-993b-0697205bbede
  Updated translation to: "Приложение Smart Switch беспрепятственно переносит..."

✓ Segment 045c01df-5072-4628-a5c3-da47ab4b38b6
  Updated translation to: "Могу ли я по-прежнему совершать видеозвонки..."

Changes saved to: russian_sample.sdlxliff
```

## Step 3: Verify (Optional)

If you want to verify the changes:

```
Show me the updated segments
```

Claude will read the file again and display the updated content.

## Custom Status Values

If you need a different status value:

```
Update the translations and set status to "rejected"
```

Or:

```
Mark segment XYZ as needs-review-translation
```

Common status values:
- `needs-translation` - Needs (re)translation
- `needs-review-translation` - Needs review
- `rejected` - Translation rejected
- `translated` - Translation complete
- `final` - Approved/final

## Working with Multiple Files

If your directory has multiple SDLXLIFF files:

```
Review all xliff files in this directory and check translations
```

Claude will:
1. Find all .sdlxliff files
2. Process each one
3. Report findings for each file
4. Update all files with corrections

## Tips

1. **Be specific about review criteria**: Tell Claude exactly what to check for
2. **Review before applying**: Always review Claude's suggestions before asking to apply them
3. **No paths needed**: When you add a directory to Cowork, you don't need to specify file paths
4. **Batch operations**: You can process multiple files in one go
5. **Custom statuses**: Use whatever status values your workflow requires

## Example: Complete Session

```
User: Read the xliff file and check Russian translations for grammar

Claude: [Analyzes file, finds 3 issues]

User: Looks good. Apply corrections and mark as needs-translation

Claude: [Updates 3 segments, saves file]

User: Great! Now check if there are any segments with placeholder text

Claude: [Searches for placeholders like {0}, {1}, etc.]
```

## Troubleshooting

If Claude can't find the file:
```
Find all SDLXLIFF files in the current directory
```

If you need to check what directory Claude is working in:
```
Use debug_sdlxliff_path to check "."
```

This will show the current working directory.
import re

# Matches ---@section Identifier ... ---@endsection
# The identifier is the first word after @section.
SECTION_PATTERN = re.compile(r'---@section\s+([A-Za-z0-9_]+)[^\n]*\n(.*?)---@endsection', re.DOTALL)

def strip_dead_sections(source: str) -> tuple[str, int]:
    """
    Iteratively strips ---@section blocks if their identifier is not referenced
    anywhere else in the source code.
    Returns (new_source, num_sections_stripped)
    """
    stripped_count = 0
    
    while True:
        # Find all sections currently in the source
        matches = list(SECTION_PATTERN.finditer(source))
        if not matches:
            break
            
        did_strip_this_pass = False
        
        for match in matches:
            identifier = match.group(1)
            full_match_text = match.group(0)
            
            # Create a version of the source without this specific section block
            # (To see if the identifier exists outside of it)
            source_without_section = source[:match.start()] + source[match.end():]
            
            # Check if identifier exists as a distinct word in the remaining source
            # Use \b to ensure a whole word match (e.g., searching 'Vec' will not match 'Vector')
            if not re.search(r'\b' + re.escape(identifier) + r'\b', source_without_section):
                # Unreferenced! Strip it.
                source = source_without_section
                stripped_count += 1
                did_strip_this_pass = True
                break # Break out of the inner loop because source has changed; re-evaluate
                
        if not did_strip_this_pass:
            # No sections were stripped during a full pass; completion condition met.
            break
            
    # Remove ---@section tags from surviving sections to save characters in the final output.
    # While handled in strip_comments, removing them here ensures cleaner intermediate states.
    source = re.sub(r'---@section[^\n]*\n', '', source)
    source = re.sub(r'---@endsection[^\n]*\n?', '', source)
            
    return source, stripped_count

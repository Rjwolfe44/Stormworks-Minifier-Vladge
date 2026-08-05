"""
VladgeMinifier - Stormworks XML Microcontroller Deployer

Provides functionality to parse Stormworks microcontroller XML structures 
and safely inject minified Lua code directly into the appropriate scripting blocks.
"""

from pathlib import Path
import xml.etree.ElementTree as ET

def deploy_to_target(lua_code: str, source_filename: str, deploy_dir: Path) -> bool:
    """
    Attempts to inject the processed Lua code into a matching .xml microcontroller file.
    
    If `deploy_dir` specifies an exact file, it injects into that file. 
    If `deploy_dir` is a directory, it attempts to locate an .xml file sharing 
    the same base name as the original Lua source file.
    
    Args:
        lua_code (str): The minified Lua payload to inject.
        source_filename (str): The name of the original script file.
        deploy_dir (Path): The target deployment directory or explicit XML file path.
        
    Returns:
        bool: True if successfully injected into an XML block, False if it fell back to a standard .lua file copy.
    """
    if not deploy_dir.exists():
        deploy_dir.mkdir(parents=True, exist_ok=True)

    if deploy_dir.is_file():
        target_xml = deploy_dir
    else:
        # Attempt to match source files to XML targets, e.g., "MyController.lua" -> "MyController.xml"
        base_name = Path(source_filename).stem
        target_xml = deploy_dir / f"{base_name}.xml"

    if target_xml.exists() and target_xml.suffix.lower() == ".xml":
        try:
            tree = ET.parse(target_xml)
            root = tree.getroot()
            
            # Locate all XML elements matching <c type="56">, which designate Lua Script blocks in Stormworks
            lua_blocks = []
            for c in root.findall(".//c"):
                if c.get("type") == "56":
                    obj = c.find("object")
                    if obj is not None and "script" in obj.attrib:
                        lua_blocks.append(obj)
            
            if lua_blocks:
                # By default, inject the code into the first identified Lua block.
                # If the filename contains a numeric prefix (e.g., "1_MyController.lua"), 
                # we use that number to target a specific index within the microcontroller.
                target_block = lua_blocks[0]
                
                # Check for a specific numeric index prefix in the filename (e.g., "2_Controller.lua" targets the 2nd Lua block)
                parts = base_name.split("_", 1)
                if len(parts) == 2 and parts[0].isdigit():
                    idx = int(parts[0]) - 1
                    if 0 <= idx < len(lua_blocks):
                        target_block = lua_blocks[idx]
                
                target_block.set("script", lua_code)
                tree.write(target_xml, encoding="UTF-8", xml_declaration=True)
                return True
        except Exception as e:
            print(f"Warning: Failed to parse or modify XML {target_xml}: {e}")
            
    # Fallback Mechanism: If no valid XML target is found or an error occurs, save standard .lua in the deployment directory
    fallback_path = deploy_dir if deploy_dir.is_file() else deploy_dir / source_filename
    fallback_path.write_text(lua_code, encoding="utf-8")
    return False

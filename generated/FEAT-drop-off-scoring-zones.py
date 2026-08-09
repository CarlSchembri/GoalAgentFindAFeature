"""
Unreal Editor Python Scripting fallback for FEAT-drop-off-scoring-zones (Drop-Off Scoring Zones).

Run from Window > Developer Tools > Python Console (or Tools > Execute Python Script) with the
GetOnDaBus project open. This is a standalone record of / fallback for the same build already
done live via unreal-mcp in this session: a Struct_ScoringTier-backed DT_DropOffScoringTiers
DataTable with 5 rows transcribed from Docs/GDD.md Section 8, plus two new variables on
BP_Destination (ScoringTiersTable, LastScoredTier).

One step this script cannot do for you: creating Struct_ScoringTier itself.
FStructureEditorUtils (the engine code that adds typed fields to a UserDefinedStruct) is
C++-only editor code with no Python/Blueprint binding -- confirmed both here and via the
unreal-mcp toolset, which exposes no struct-creation tool at all. If the struct doesn't exist
yet, this script prints the fields to add by hand and stops before touching anything else.

Struct_ScoringTier fields (create via Content Browser > Add > Blueprint > Structure):
    TierName            (Name)
    DisplayLabel         (Text)
    TimeBonusSeconds     (Integer)
    MoneyBonus           (Integer)
"""

import unreal

STRUCT_PATH = "/Game/BP/Data/Struct_ScoringTier"
DATATABLE_FOLDER = "/Game/BP/Data"
DATATABLE_NAME = "DT_DropOffScoringTiers"
DATATABLE_PATH = f"{DATATABLE_FOLDER}/{DATATABLE_NAME}"
BP_DESTINATION_PATH = "/Game/BP/Destination/BP_Destination"

# Name, TierName, DisplayLabel, TimeBonusSeconds, MoneyBonus -- straight from GDD Section 8.
SCORING_TIER_CSV = """Name,TierName,DisplayLabel,TimeBonusSeconds,MoneyBonus
Awful,Awful,Awful,0,0
Bad,Bad,Bad,4,1
OK,OK,OK,8,5
Good,Good,Good,12,10
Perfect,Perfect,Perfect!,18,15
"""


def create_scoring_datatable() -> unreal.DataTable | None:
    if not unreal.EditorAssetLibrary.does_asset_exist(STRUCT_PATH):
        print(f"[FEAT-drop-off-scoring-zones] {STRUCT_PATH} does not exist yet.")
        print("Create it by hand first: Content Browser > Add > Blueprint > Structure,")
        print("named Struct_ScoringTier, with fields:")
        print("  TierName (Name), DisplayLabel (Text), TimeBonusSeconds (Integer), MoneyBonus (Integer)")
        return None

    if unreal.EditorAssetLibrary.does_asset_exist(DATATABLE_PATH):
        print(f"[FEAT-drop-off-scoring-zones] {DATATABLE_PATH} already exists -- skipping creation.")
        return unreal.load_asset(DATATABLE_PATH)

    struct = unreal.load_object(None, STRUCT_PATH)
    factory = unreal.DataTableFactory()
    factory.struct = struct

    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    data_table = asset_tools.create_asset(DATATABLE_NAME, DATATABLE_FOLDER, unreal.DataTable, factory)

    problems = unreal.DataTableFunctionLibrary.fill_data_table_from_csv_string(data_table, SCORING_TIER_CSV)
    if problems:
        print(f"[FEAT-drop-off-scoring-zones] CSV import reported problems: {problems}")
    else:
        print(f"[FEAT-drop-off-scoring-zones] Populated {DATATABLE_PATH} with 5 rows.")

    unreal.EditorAssetLibrary.save_loaded_asset(data_table)
    return data_table


def wire_bp_destination(data_table: unreal.DataTable) -> None:
    if not unreal.EditorAssetLibrary.does_asset_exist(BP_DESTINATION_PATH):
        print(f"[FEAT-drop-off-scoring-zones] {BP_DESTINATION_PATH} not found -- skipping BP wiring.")
        return

    blueprint = unreal.load_asset(BP_DESTINATION_PATH)
    generated_class = blueprint.generated_class()
    cdo = unreal.get_default_object(generated_class)

    # Adding NEW member variables to a Blueprint has no supported pure-Python API (unlike
    # unreal-mcp's dedicated BlueprintTools, which drives the same internal editor subsystem
    # this console can't reach directly). If ScoringTiersTable/LastScoredTier were already
    # added -- by this session's unreal-mcp run, or by hand -- this sets their default value.
    # Otherwise it prints the same instructions a human would follow in the Blueprint editor.
    has_table_var = cdo.get_editor_property("ScoringTiersTable") is not None or hasattr(cdo, "ScoringTiersTable")
    try:
        cdo.set_editor_property("ScoringTiersTable", data_table)
        cdo.set_editor_property("LastScoredTier", unreal.Name("None"))
        unreal.EditorAssetLibrary.save_loaded_asset(blueprint)
        print(f"[FEAT-drop-off-scoring-zones] Set BP_Destination.ScoringTiersTable = {DATATABLE_PATH}")
    except Exception as exc:
        print(f"[FEAT-drop-off-scoring-zones] Could not set BP_Destination variables ({exc}).")
        print("Add these two variables by hand in the Blueprint editor's My Blueprint panel first:")
        print("  ScoringTiersTable (Object Reference -> DataTable), default = DT_DropOffScoringTiers")
        print("  LastScoredTier (Name)")


if __name__ == "__main__":
    table = create_scoring_datatable()
    if table is not None:
        wire_bp_destination(table)

export interface AppSettings {
  journal_directory: string;
  inara_api_key: string | null;
  /**
   * When true (default), systems where this commander's journals contain
   * colonisation sites are served purely from local journal data. Inara is
   * only consulted for systems with no local colonisation data. When false,
   * Inara data is preferred wherever it is available.
   */
  prefer_local_for_commander_systems: boolean;
}
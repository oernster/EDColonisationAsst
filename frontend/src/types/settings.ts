export interface AppSettings {
  /**
   * The one user-editable setting. The dormant Inara configuration is not
   * settable from the UI and the commander's name is journal-derived.
   */
  journal_directory: string;
}

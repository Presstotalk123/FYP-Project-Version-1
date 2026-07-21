export interface ErdPromptVersionSummary {
  version_no: number;
  content: string;
  created_by_email: string | null;
  created_at: string | null;
  is_active: boolean;
}

export interface ErdPromptListItem {
  key: string;
  label: string;
  description: string;
  default_content: string;
  is_overridden: boolean;
  active: ErdPromptVersionSummary | null;
}

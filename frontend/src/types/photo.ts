export interface PropertyPhoto {
  id: string;
  property_id: string;
  water_feature_id: string | null;
  filename: string;
  url: string;
  caption: string | null;
  is_hero: boolean;
  uploaded_by: string | null;
  created_at: string;
}

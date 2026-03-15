export interface PropertyPhoto {
  id: string;
  property_id: string;
  body_of_water_id: string | null;
  filename: string;
  url: string;
  caption: string | null;
  is_hero: boolean;
  uploaded_by: string | null;
  created_at: string;
}

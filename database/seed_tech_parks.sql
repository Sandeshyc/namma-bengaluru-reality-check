-- Insert Tech Parks into the reference table
INSERT INTO tech_parks (id, name, latitude, longitude) VALUES
('tp_manyata', 'Manyata Tech Park', 13.0493, 77.6198),
('tp_whitefield', 'Whitefield (ITPB)', 12.9698, 77.7500),
('tp_ecity', 'Electronic City', 12.8458, 77.6612),
('tp_bagmane', 'Bagmane Tech Park (ORR)', 12.9545, 77.6347),
('tp_marathahalli', 'Marathahalli', 12.9588, 77.6972)
ON CONFLICT (id) DO UPDATE 
SET name = EXCLUDED.name, 
    latitude = EXCLUDED.latitude, 
    longitude = EXCLUDED.longitude;

INSERT INTO farms (farm_name, location, total_area_acres)
VALUES ('Moses Farm', 'Nakuru, Kenya', 3.0);
INSERT INTO market_areas (area_name, region) VALUES
('Nakuru Central', 'Nakuru County'),
('Nakuru North', 'Nakuru County'),
('Naivasha', 'Nakuru County');
INSERT INTO fields (farm_id, field_name, area_acres, soil_type, notes)
VALUES
(1, 'Field 1', 1.5, 'Loam', ''),
(1, 'Field 2', 1.0, 'Clay', ''),
(1, 'Field 3', 0.5, 'Sandy Loam', '');

INSERT INTO crops (farm_id, field_id, crop_name, variety, planting_date, expected_harvest_date, area_acres, status)
VALUES
(1, 1, 'Maize', 'H614', date('now', '-33 days'), date('now', '+35 days'), 1.5, 'growing'),
(1, 2, 'Beans', 'Rosecoco', date('now', '-15 days'), date('now', '+25 days'), 1.0, 'growing'),
(1, 3, 'Kale', 'Sukuma Wiki', date('now', '-45 days'), date('now', '+15 days'), 0.5, 'growing');

INSERT INTO activities (farm_id, crop_id, activity_date, activity_type, crop_name, input_used, quantity, notes)
VALUES
(1, 1, date('now', '-2 days'), 'Fertilizer application', 'Maize', 'DAP', '50kg', ''),
(1, 2, date('now', '-4 days'), 'Weeding', 'Beans', '', '', ''),
(1, 3, date('now', '-5 days'), 'Irrigation', 'Kale', 'Water', '200L', ''),
(1, 1, date('now', '-7 days'), 'Pest control', 'Maize', 'Pesticide', '2L', '');

INSERT INTO soil_tests (farm_id, field_id, test_date, soil_type, ph, nitrogen, phosphorus, potassium, organic_matter, moisture, notes)
VALUES
(1, 1, date('now', '-20 days'), 'Loam', 6.4, 28, 15, 110, 2.6, 22, '');

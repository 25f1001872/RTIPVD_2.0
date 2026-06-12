from src.geospatial.zone_checker import NoParkingZoneChecker
import json
import os

geojson = {
    'type': 'FeatureCollection',
    'features': [
        {
            'type': 'Feature',
            'properties': {
                'zone_id': 'ROAD-123',
                'name': 'Main Street',
                'buffer_meters': 10.0
            },
            'geometry': {
                'type': 'LineString',
                'coordinates': [
                    [10.0, 10.0],
                    [10.0001, 10.0]
                ]
            }
        }
    ]
}

with open('test_zones.geojson', 'w') as f:
    json.dump(geojson, f)

checker = NoParkingZoneChecker(enabled=True, geojson_path='test_zones.geojson')
print('Loaded checking lines')
m1 = checker.find_zone(10.0, 10.00005) # lat, lon (this point is literally inside the segment in X, same Y)
m2 = checker.find_zone(10.0, 10.0005) # lat, lon (this one is outside buffer X)

print('Match 1 (should match):', m1)
print('Match 2 (should not match):', m2)
import unittest
from tools.pr13_resource_policy import memory_causes, launch_memory_ready, latency_causes


class ResourcePolicyTests(unittest.TestCase):
    def test_absolute_floor_boundary_and_no_legacy_percent_stop(self):
        resource = {'memory_available': 10, 'memory_available_bytes': 500_000_000}
        generator = {'available': True, 'host_memory_available_bytes': 500_000_000}
        self.assertEqual(memory_causes(resource, generator, 500_000_000, 500_000_000), [])
        resource['memory_available_bytes'] -= 1
        generator['host_memory_available_bytes'] -= 1
        self.assertEqual(memory_causes(resource, generator, 500_000_000, 500_000_000),
                         ['memory_available_bytes_redline', 'generator_memory_low'])

    def test_missing_or_invalid_cloud_bytes_cannot_fall_back_to_percent(self):
        for value in [None, True, -1, float('nan'), float('inf')]:
            self.assertIn('monitoring_unavailable', memory_causes(
                {'memory_available': 90, 'memory_available_bytes': value},
                {'available': True, 'host_memory_available_bytes': 3 * 1024 ** 3}, 500_000_000, 500_000_000))

    def test_legacy_profile_retains_original_floors(self):
        self.assertEqual(memory_causes({'memory_available': 14},
                         {'available': True, 'host_memory_available_bytes': 2 * 1024 ** 3 - 1}),
                         ['memory_available_redline', 'generator_memory_low'])

    def test_absent_generator_monitoring_is_not_safe(self):
        self.assertIn('generator_memory_monitoring_unavailable', memory_causes({'memory_available': 90}, {}))

    def test_launch_reserve_is_added_to_new_floor(self):
        required = 500_000_000 + 64 * 1024 ** 2
        self.assertTrue(launch_memory_ready(required, 500_000_000, 64))
        self.assertFalse(launch_memory_ready(required - 1, 500_000_000, 64))

    def test_north_america_profile_does_not_rewrite_default_latency(self):
        window={'valid_latency_count':20,'http':{'p95_ms':4000},'realtime':{'count':10,'p95_ms':6000}}
        health={'ok':True,'duration_ms':9000}
        self.assertEqual(latency_causes(window,health),['health_failed_or_over_5000ms','http_p95_over_1500ms','command_p95_over_2000ms'])
        self.assertEqual(latency_causes(window,health,5000,8000,10000),[])

    def test_north_america_boundaries_and_health_failure_remain_stops(self):
        window={'valid_latency_count':20,'http':{'p95_ms':5000},'realtime':{'count':10,'p95_ms':8000}}
        health={'ok':True,'duration_ms':10000}
        self.assertEqual(latency_causes(window,health,5000,8000,10000),[])
        window['http']['p95_ms']+=1;window['realtime']['p95_ms']+=1;health['duration_ms']+=1
        self.assertEqual(latency_causes(window,health,5000,8000,10000),['health_failed_or_over_10000ms','http_p95_over_5000ms','command_p95_over_8000ms'])
        health={'ok':False,'duration_ms':1}
        self.assertIn('health_failed_or_over_10000ms',latency_causes(window,health,5000,8000,10000))

"""
Load Testing Script for ETag Performance Evaluation.

This script performs comprehensive load testing to measure:
1. Response times with/without ETags
2. Cache hit rates
3. Database query performance
4. Bandwidth savings

Usage:
    python tests/load_test.py
"""

import asyncio
import aiohttp
import time
import statistics
from typing import List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import json


@dataclass
class TestResult:
    """Individual test request result."""
    request_num: int
    response_time_ms: float
    status_code: int
    has_etag: bool
    used_etag: bool
    response_size_bytes: int
    is_304: bool


@dataclass
class TestScenario:
    """Test scenario configuration."""
    name: str
    description: str
    num_requests: int
    use_etag: bool
    user_id: int = 1


@dataclass
class PerformanceReport:
    """Comprehensive performance analysis report."""
    scenario_name: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    
    # Response times
    avg_response_time_ms: float
    min_response_time_ms: float
    max_response_time_ms: float
    median_response_time_ms: float
    p95_response_time_ms: float
    p99_response_time_ms: float
    
    # Cache metrics
    cache_hit_count: int = 0
    cache_miss_count: int = 0
    cache_hit_rate: float = 0.0
    
    # Status codes
    status_200_count: int = 0
    status_304_count: int = 0
    
    # Data transfer
    total_bytes_transferred: int = 0
    avg_response_size_bytes: float = 0.0
    
    # Throughput
    total_duration_seconds: float = 0.0
    requests_per_second: float = 0.0
    
    # Raw data
    results: List[TestResult] = field(default_factory=list)


class LoadTester:
    """
    Load testing client for ETag performance evaluation.
    
    Performs various test scenarios and generates comprehensive reports.
    """
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        Initialize load tester.
        
        Args:
            base_url: Base URL of the API to test
        """
        self.base_url = base_url
        self.session: aiohttp.ClientSession | None = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def make_request(
        self, 
        user_id: int, 
        etag: str | None = None,
        request_num: int = 0
    ) -> TestResult:
        """
        Make a single request to the API.
        
        Args:
            user_id: User ID to fetch
            etag: ETag to include in If-None-Match header
            request_num: Request number for tracking
            
        Returns:
            TestResult with timing and response information
        """
        url = f"{self.base_url}/users/{user_id}"
        headers = {}
        
        if etag:
            headers["If-None-Match"] = etag
        
        start = time.perf_counter()
        
        async with self.session.get(url, headers=headers) as response:
            end = time.perf_counter()
            
            response_time_ms = (end - start) * 1000
            status_code = response.status
            response_etag = response.headers.get("ETag")
            
            # Get response size
            if status_code == 304:
                response_size = 0
            else:
                content = await response.text()
                response_size = len(content.encode('utf-8'))
            
            return TestResult(
                request_num=request_num,
                response_time_ms=response_time_ms,
                status_code=status_code,
                has_etag=response_etag is not None,
                used_etag=etag is not None,
                response_size_bytes=response_size,
                is_304=(status_code == 304)
            )
    
    async def run_scenario(self, scenario: TestScenario) -> PerformanceReport:
        """
        Run a complete test scenario.
        
        Args:
            scenario: Test scenario configuration
            
        Returns:
            PerformanceReport with comprehensive metrics
        """
        print(f"\n{'='*70}")
        print(f"Running: {scenario.name}")
        print(f"Description: {scenario.description}")
        print(f"Requests: {scenario.num_requests}")
        print(f"{'='*70}\n")
        
        results: List[TestResult] = []
        etag_to_use = None
        
        # First request to get initial ETag if needed
        if scenario.use_etag:
            print("📋 Performing initial request to get ETag...")
            first_result = await self.make_request(scenario.user_id, None, 0)
            
            # Get ETag from response (we need to make another request to get it)
            url = f"{self.base_url}/users/{scenario.user_id}"
            async with self.session.get(url) as response:
                etag_to_use = response.headers.get("ETag")
                print(f"✅ Got ETag: {etag_to_use}\n")
        
        # Run load test
        print(f"🚀 Starting load test ({scenario.num_requests} requests)...")
        start_time = time.perf_counter()
        
        for i in range(scenario.num_requests):
            result = await self.make_request(
                scenario.user_id, 
                etag_to_use if scenario.use_etag else None,
                i + 1
            )
            results.append(result)
            
            # Progress indicator
            if (i + 1) % 10 == 0 or (i + 1) == scenario.num_requests:
                print(f"  Progress: {i + 1}/{scenario.num_requests} requests", end='\r')
        
        end_time = time.perf_counter()
        total_duration = end_time - start_time
        
        print(f"\n✅ Load test completed in {total_duration:.2f}s\n")
        
        # Generate report
        return self._generate_report(scenario.name, results, total_duration)
    
    def _generate_report(
        self, 
        scenario_name: str, 
        results: List[TestResult],
        total_duration: float
    ) -> PerformanceReport:
        """
        Generate comprehensive performance report from test results.
        
        Args:
            scenario_name: Name of the test scenario
            results: List of test results
            total_duration: Total test duration in seconds
            
        Returns:
            PerformanceReport with all metrics
        """
        if not results:
            return PerformanceReport(
                scenario_name=scenario_name,
                total_requests=0,
                successful_requests=0,
                failed_requests=0,
                avg_response_time_ms=0,
                min_response_time_ms=0,
                max_response_time_ms=0,
                median_response_time_ms=0,
                p95_response_time_ms=0,
                p99_response_time_ms=0
            )
        
        # Extract metrics
        response_times = [r.response_time_ms for r in results]
        response_times_sorted = sorted(response_times)
        
        successful = [r for r in results if r.status_code in [200, 304]]
        failed = [r for r in results if r.status_code not in [200, 304]]
        
        status_200 = [r for r in results if r.status_code == 200]
        status_304 = [r for r in results if r.status_code == 304]
        
        total_bytes = sum(r.response_size_bytes for r in results)
        
        # Calculate percentiles
        def percentile(data: List[float], p: float) -> float:
            if not data:
                return 0.0
            k = (len(data) - 1) * p
            f = int(k)
            c = f + 1 if f + 1 < len(data) else f
            return data[f] + (k - f) * (data[c] - data[f])
        
        # Cache metrics (304 responses indicate cache hits)
        cache_hits = len(status_304)
        cache_misses = len(status_200)
        cache_hit_rate = (cache_hits / len(results) * 100) if results else 0
        
        return PerformanceReport(
            scenario_name=scenario_name,
            total_requests=len(results),
            successful_requests=len(successful),
            failed_requests=len(failed),
            
            avg_response_time_ms=statistics.mean(response_times),
            min_response_time_ms=min(response_times),
            max_response_time_ms=max(response_times),
            median_response_time_ms=statistics.median(response_times),
            p95_response_time_ms=percentile(response_times_sorted, 0.95),
            p99_response_time_ms=percentile(response_times_sorted, 0.99),
            
            cache_hit_count=cache_hits,
            cache_miss_count=cache_misses,
            cache_hit_rate=cache_hit_rate,
            
            status_200_count=len(status_200),
            status_304_count=len(status_304),
            
            total_bytes_transferred=total_bytes,
            avg_response_size_bytes=total_bytes / len(results) if results else 0,
            
            total_duration_seconds=total_duration,
            requests_per_second=len(results) / total_duration if total_duration > 0 else 0,
            
            results=results
        )
    
    def print_report(self, report: PerformanceReport):
        """
        Print formatted performance report.
        
        Args:
            report: PerformanceReport to display
        """
        print(f"\n{'='*70}")
        print(f"PERFORMANCE REPORT: {report.scenario_name}")
        print(f"{'='*70}\n")
        
        print("📊 REQUEST SUMMARY")
        print(f"  Total Requests:      {report.total_requests}")
        print(f"  Successful:          {report.successful_requests} ({report.successful_requests/report.total_requests*100:.1f}%)")
        print(f"  Failed:              {report.failed_requests}")
        print(f"  Duration:            {report.total_duration_seconds:.2f}s")
        print(f"  Throughput:          {report.requests_per_second:.2f} req/s\n")
        
        print("⏱️  RESPONSE TIME METRICS (ms)")
        print(f"  Average:             {report.avg_response_time_ms:.2f} ms")
        print(f"  Median:              {report.median_response_time_ms:.2f} ms")
        print(f"  Min:                 {report.min_response_time_ms:.2f} ms")
        print(f"  Max:                 {report.max_response_time_ms:.2f} ms")
        print(f"  95th Percentile:     {report.p95_response_time_ms:.2f} ms")
        print(f"  99th Percentile:     {report.p99_response_time_ms:.2f} ms\n")
        
        print("💾 CACHE PERFORMANCE")
        print(f"  Cache Hits (304):    {report.cache_hit_count}")
        print(f"  Cache Misses (200):  {report.cache_miss_count}")
        print(f"  Cache Hit Rate:      {report.cache_hit_rate:.1f}%\n")
        
        print("📦 DATA TRANSFER")
        print(f"  Total Bytes:         {report.total_bytes_transferred:,} bytes")
        print(f"  Avg Response Size:   {report.avg_response_size_bytes:.2f} bytes")
        print(f"  200 Responses:       {report.status_200_count}")
        print(f"  304 Responses:       {report.status_304_count}\n")
    
    def compare_reports(self, report1: PerformanceReport, report2: PerformanceReport):
        """
        Compare two performance reports and show improvements.
        
        Args:
            report1: Baseline report (without ETags)
            report2: Comparison report (with ETags)
        """
        print(f"\n{'='*70}")
        print("PERFORMANCE COMPARISON")
        print(f"{'='*70}\n")
        
        print(f"Baseline:    {report1.scenario_name}")
        print(f"Optimized:   {report2.scenario_name}\n")
        
        # Response time improvement
        time_improvement = ((report1.avg_response_time_ms - report2.avg_response_time_ms) 
                           / report1.avg_response_time_ms * 100)
        
        print("⏱️  RESPONSE TIME IMPROVEMENT")
        print(f"  Baseline Avg:        {report1.avg_response_time_ms:.2f} ms")
        print(f"  Optimized Avg:       {report2.avg_response_time_ms:.2f} ms")
        print(f"  Improvement:         {time_improvement:.1f}% faster")
        print(f"  Time Saved:          {report1.avg_response_time_ms - report2.avg_response_time_ms:.2f} ms per request\n")
        
        # Throughput improvement
        throughput_improvement = ((report2.requests_per_second - report1.requests_per_second) 
                                 / report1.requests_per_second * 100)
        
        print("🚀 THROUGHPUT IMPROVEMENT")
        print(f"  Baseline:            {report1.requests_per_second:.2f} req/s")
        print(f"  Optimized:           {report2.requests_per_second:.2f} req/s")
        print(f"  Improvement:         {throughput_improvement:.1f}% increase\n")
        
        # Bandwidth savings
        bandwidth_saved = report1.total_bytes_transferred - report2.total_bytes_transferred
        bandwidth_saved_pct = (bandwidth_saved / report1.total_bytes_transferred * 100) if report1.total_bytes_transferred > 0 else 0
        
        print("📦 BANDWIDTH SAVINGS")
        print(f"  Baseline Transfer:   {report1.total_bytes_transferred:,} bytes")
        print(f"  Optimized Transfer:  {report2.total_bytes_transferred:,} bytes")
        print(f"  Bandwidth Saved:     {bandwidth_saved:,} bytes ({bandwidth_saved_pct:.1f}%)\n")
        
        # Cache effectiveness
        print("💾 CACHE EFFECTIVENESS")
        print(f"  Cache Hit Rate:      {report2.cache_hit_rate:.1f}%")
        print(f"  304 Responses:       {report2.cache_hit_count}/{report2.total_requests}")
        print(f"  DB Queries Avoided:  {report2.cache_hit_count}\n")


async def main():
    """Run comprehensive load testing scenarios."""
    
    print("\n" + "="*70)
    print("ETag Performance Load Testing Suite")
    print("="*70)
    
    # Define test scenarios
    scenarios = [
        TestScenario(
            name="Baseline - No ETags",
            description="100 requests without using ETags (cache misses)",
            num_requests=100,
            use_etag=False,
            user_id=1
        ),
        TestScenario(
            name="Optimized - With ETags",
            description="100 requests using ETags (cache hits)",
            num_requests=100,
            use_etag=True,
            user_id=1
        ),
        TestScenario(
            name="High Load - No ETags",
            description="500 requests without ETags",
            num_requests=500,
            use_etag=False,
            user_id=1
        ),
        TestScenario(
            name="High Load - With ETags",
            description="500 requests with ETags",
            num_requests=500,
            use_etag=True,
            user_id=1
        ),
    ]
    
    reports = []
    
    async with LoadTester() as tester:
        # Run all scenarios
        for scenario in scenarios:
            report = await tester.run_scenario(scenario)
            tester.print_report(report)
            reports.append(report)
            
            # Small delay between scenarios
            await asyncio.sleep(2)
        
        # Generate comparisons
        if len(reports) >= 2:
            print("\n")
            tester.compare_reports(reports[0], reports[1])
        
        if len(reports) >= 4:
            print("\n")
            tester.compare_reports(reports[2], reports[3])
        
        # Save reports to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"load_test_report_{timestamp}.json"
        
        with open(report_file, 'w') as f:
            report_data = {
                "timestamp": timestamp,
                "scenarios": [
                    {
                        "name": r.scenario_name,
                        "total_requests": r.total_requests,
                        "avg_response_time_ms": r.avg_response_time_ms,
                        "cache_hit_rate": r.cache_hit_rate,
                        "throughput_rps": r.requests_per_second,
                        "total_bytes": r.total_bytes_transferred
                    }
                    for r in reports
                ]
            }
            json.dump(report_data, f, indent=2)
        
        print(f"\n📄 Report saved to: {report_file}")
        print(f"\n{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())

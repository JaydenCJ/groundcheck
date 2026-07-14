# Cache design

Reads are served from a write-through cache in front of the primary store.
Cache entries expire after 300 seconds, and expiry is enforced by a background
sweeper that runs once per minute. During the 2025 load test the cache
absorbed 92% of read traffic at the p99 latency target of 12 ms.

Writes go straight to the primary store and invalidate the corresponding
cache entry in the same transaction. A cold start refills the cache lazily;
there is no warm-up job.

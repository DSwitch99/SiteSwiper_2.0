"""Configuration constants for SiteSwiper."""

import os
from pathlib import Path

# NTP servers for time synchronization (queried in order, median offset used)
NTP_SERVERS = [
    "time.google.com",
    "pool.ntp.org",
    "time.nist.gov",
]

# Default booking time
DEFAULT_FIRE_HOUR = 7
DEFAULT_FIRE_MINUTE = 0
DEFAULT_FIRE_SECOND = 0

# Timezone for Ontario Parks
TIMEZONE = "America/Toronto"

# Precision timing thresholds
SPIN_WAIT_THRESHOLD_SECONDS = 2.0  # Switch to spin-wait this many seconds before T-0
SLEEP_INTERVAL_SECONDS = 0.5       # Sleep interval during countdown (before spin-wait)

# Retry settings
DEFAULT_MAX_RETRIES = 5
DEFAULT_RETRY_DELAY_MS = 100  # Milliseconds between retries

# Pre-fire offset: fire this many ms before the target time to compensate for network latency
DEFAULT_PREFIRE_OFFSET_MS = 0  # 0 = disabled; try 50-200ms based on your measured round-trip time

# Connection pre-warm timing
PREWARM_SECONDS_BEFORE = 10  # Pre-warm connection this many seconds before T-0

# Request storage
STORAGE_DIR = Path(os.path.expanduser("~/.siteswiper/requests"))

# Response logs
LOG_DIR = Path(os.path.expanduser("~/.siteswiper/logs"))

# Session cookie freshness warning (hours)
COOKIE_FRESHNESS_WARNING_HOURS = 4

# Request timeout
REQUEST_TIMEOUT_SECONDS = 30

# ---------------------------------------------------------------------------
# Campsite lookup table
# Each entry: (campsite_name, campsite_number, site_id)
# ---------------------------------------------------------------------------
CAMPSITES: list[tuple[str, int, int]] = [
    ("Granite Saddle", 1034, -2147475109),
    ("Granite Saddle", 1036, -2147474728),
    ("Granite Saddle", 1037, -2147474328),
    ("Granite Saddle", 1038, -2147474445),
    ("Granite Saddle", 1039, -2147475127),
    ("Granite Saddle", 1040, -2147474942),
    ("Granite Saddle", 1041, -2147474676),
    ("Granite Saddle", 1042, -2147474731),
    ("Granite Saddle", 1043, -2147474493),
    ("Granite Saddle", 1044, -2147474539),
    ("Granite Saddle", 1045, -2147474627),
    ("Granite Saddle", 1046, -2147474326),
    ("Granite Saddle", 1047, -2147474261),
    ("Granite Saddle", 1048, -2147474988),
]

# Reverse lookup: site_id -> (campsite_name, campsite_number)
CAMPSITE_BY_SITE_ID: dict[int, tuple[str, int]] = {
    site_id: (name, number) for name, number, site_id in CAMPSITES
}

# ---------------------------------------------------------------------------
# Built-in preset template
# A real captured Ontario Parks cart/commit cURL that users can load instead
# of having to capture their own.  Edit booking fields (dates, site/park IDs)
# and refresh cookies before use.
# ---------------------------------------------------------------------------
PRESET_CURL = (
    "curl 'https://reservations.ontarioparks.ca/api/cart/commit?isCompleted=false&isSelfCheckIn=false'"
    " -H 'Accept: application/json, text/plain, */*'"
    " -H 'Accept-Language: en-US,en;q=0.9'"
    " -H 'App-Language: en-CA'"
    " -H 'Cache-Control: no-cache'"
    " -H 'Connection: keep-alive'"
    " -H 'Content-Type: application/json'"
    " -b '_ga=GA1.1.687088662.1769193672; ai_user=1Zng2/weRKeBBvrxVaBMJo|2026-01-23T18:41:12.803Z;"
    " .AspNetCore.Antiforgery.3YREhQdkuHQ=CfDJ8IbQUbNaZPtJut3m8OUV9VYVvdfdd_xJT4OJtZuB1pC6aHsmc4AbhMzuhhcFMLVhkf_b0PrMdtTBdKkNkQaXSWGWaJxks8Bw96kzwLXuJWUQ9WNA2C1JKRpPf9V32BRiIB37R7cmb-OHGiuh1ZGbsic;"
    " prime-session=CfDJ8IbQUbNaZPtJut3m8OUV9VbvA_nCVNvHLafmEB2D7QCgR6gG_YLI6fOfdcE9Xpxr4QZ7DhOeHG5OoJdIyebKsshgftheqOuBC-FqmEArFZhgJlsBsE5477ZB4bbr8XNOvIdlFqe2nORjVYaSTTDGXb9MNHhzC4-OSzrXqcLI-dI-Qz3HJC4NFQBsV_4ufP6CGw0aWtJAWp04nLQfLvWBtCMfPFG6HyWSmrcojFfQNClt-d2ehFZX0vGDI0QqPWJqauonmgu0GV_4410nX7h2pjT5T7ScDEua4LP-6vop5JhhbE3_mnQ2n_wlbIUhe9llKLFOJy2iq36zZsy9yACsCNE;"
    " isLoggedIn=true;"
    " XSRF-TOKEN=CfDJ8IbQUbNaZPtJut3m8OUV9Vaz0B-I99-p6zmQuCsO7R0wy8yGlXGP0n8F5fymjuuMudbnnOChc1sUpN4UucmgTsSVA8K7jTS_-sbXq7En2-u6lLpGl1P---i-up7ek2Jq4M6SKfLjPIBl7DGbCy0gF5pDWtZNomtKd7RM1zz2Uz_DU2z_060MErZ3ai6eNKjVQA'"
    " -H 'Expires: 0'"
    " -H 'Origin: https://reservations.ontarioparks.ca'"
    " -H 'Pragma: no-cache'"
    " -H 'Referer: https://reservations.ontarioparks.ca/create-booking/results?transactionLocationId=-2147483596&resourceLocationId=-2147483600&mapId=-2147483421&searchTabGroupId=0&bookingCategoryId=0&startDate=2026-05-20&endDate=2026-05-21&nights=1&isReserving=true&equipmentId=-32768&subEquipmentId=-32768&peopleCapacityCategoryCounts=%5B%5B-32768,null,1,null%5D%5D&searchTime=2026-03-04T09:02:34.574&flexibleSearch=%5Bfalse,false,%222026-03-01%22,1%5D&filterData=%7B%22-32736%22:%22%5B%5B1%5D,0,0,0%5D%22,%22-32726%22:%22%5B%5B1%5D,0,0,0%5D%22%7D'"
    " -H 'Sec-Fetch-Dest: empty'"
    " -H 'Sec-Fetch-Mode: cors'"
    " -H 'Sec-Fetch-Site: same-origin'"
    " -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36'"
    " -H 'X-XSRF-TOKEN: CfDJ8IbQUbNaZPtJut3m8OUV9Vaz0B-I99-p6zmQuCsO7R0wy8yGlXGP0n8F5fymjuuMudbnnOChc1sUpN4UucmgTsSVA8K7jTS_-sbXq7En2-u6lLpGl1P---i-up7ek2Jq4M6SKfLjPIBl7DGbCy0gF5pDWtZNomtKd7RM1zz2Uz_DU2z_060MErZ3ai6eNKjVQA'"
    " -H 'app-version: 5.106.226'"
    " -H 'sec-ch-ua: \"Not:A-Brand\";v=\"99\", \"Google Chrome\";v=\"145\", \"Chromium\";v=\"145\"'"
    " -H 'sec-ch-ua-mobile: ?0'"
    " -H 'sec-ch-ua-platform: \"Windows\"'"
    " --data-raw '{\"cart\":{\"cartUid\":\"e65aaf27-b03c-491b-a925-1ac9d30417d2\",\"createTransactionUid\":\"41ae6b36-0473-4b9c-bf2a-f536ad06f7ab\",\"shopperUid\":null,\"groupUid\":null,\"referenceNumberPrefix\":\"INOP25\",\"referenceNumberSuffix\":\"18011760\",\"newTransaction\":{\"cartTransactionUid\":\"41ae6b36-0473-4b9c-bf2a-f536ad06f7ab\",\"cartUid\":\"00000000-0000-0000-0000-000000000000\",\"completeDate\":null,\"createDate\":\"2026-03-04T14:02:23.613Z\",\"editBookingLock\":false,\"lastEditDate\":\"2026-03-04T14:02:23.711Z\",\"referenceNumberPrefix\":\"INOP25\",\"referenceNumberSuffix\":\"18011760\",\"shiftUid\":\"b596fb6d-f648-4057-bb30-bd320c80cda6\",\"shopperUid\":\"39880c83-f551-4684-bb50-6777e533af82\",\"status\":1,\"terminalLocationId\":-2147483604,\"transactionBookings\":[],\"transactionSales\":[],\"transactionShipments\":[],\"userUid\":\"3e094c48-0eea-40cf-bb41-5bf11fe9c7e9\"},\"transactionDrafts\":[],\"transactionHistory\":[],\"giftCards\":[],\"sales\":[],\"bookings\":[{\"bookingUid\":\"0215a75b-1117-4f30-bfbd-fef6d64aa21f\",\"cartUid\":\"e65aaf27-b03c-491b-a925-1ac9d30417d2\",\"bookingCategoryId\":0,\"bookingModel\":0,\"newVersion\":{\"cartTransactionUid\":\"41ae6b36-0473-4b9c-bf2a-f536ad06f7ab\",\"bookingMembers\":[],\"bookingVehicles\":[],\"bookingBoats\":[],\"bookingCapacityCategoryCounts\":[{\"capacityCategoryId\":-32768,\"subCapacityCategoryId\":null,\"count\":1}],\"rateCategoryId\":-32768,\"resourceBlockerUids\":[\"24ea5098-2eca-48bb-ac72-b636328cb353\"],\"resourceNonSpecificBlockerUids\":[],\"resourceZoneBlockerUids\":[],\"resourceZoneEntryBlockerUids\":[],\"startDate\":\"2026-05-20\",\"endDate\":\"2026-05-21\",\"releasePersonalInformation\":false,\"equipmentCategoryId\":-32768,\"subEquipmentCategoryId\":-32768,\"occupant\":{\"contact\":{\"email\":\"\",\"contactName\":\"\",\"phoneNumberCountryCode\":null,\"phoneNumber\":\"\"},\"address\":{},\"allowMarketing\":false,\"phoneNumbers\":{},\"preferredCultureName\":\"en-CA\",\"firstName\":\"DANIEL\",\"lastName\":\"SHAVER\"},\"requiresCheckout\":false,\"bookingStatus\":0,\"completedDate\":\"2026-03-04T14:02:34.900Z\",\"arrivalComment\":\"\",\"entryPointResourceId\":null,\"exitPointResourceId\":null,\"bookingSurcharges\":[],\"consentToRelease\":false,\"equipmentDescription\":\"\",\"groupHoldUid\":\"\",\"organizationName\":\"\",\"passExpiryDate\":null,\"passNumber\":\"\",\"resourceLocationId\":-2147483600,\"checkInTime\":null,\"checkOutTime\":null,\"deferredPayment\":false},\"createTransactionUid\":\"41ae6b36-0473-4b9c-bf2a-f536ad06f7ab\",\"currentVersion\":null,\"history\":[],\"drafts\":[],\"referenceNumberPostfix\":\"\"}],\"shipments\":[],\"groupHold\":null,\"paymentGroups\":[],\"gatewayPaymentSessions\":[],\"lineItems\":[],\"resourceBlockers\":[{\"blockerType\":0,\"cartUid\":\"e65aaf27-b03c-491b-a925-1ac9d30417d2\",\"resourceBlockerUid\":\"24ea5098-2eca-48bb-ac72-b636328cb353\",\"bookingUid\":\"0215a75b-1117-4f30-bfbd-fef6d64aa21f\",\"groupHoldUid\":\"\",\"isReservation\":true,\"newVersion\":{\"creationDate\":\"2026-03-04T14:02:48.379Z\",\"cartTransactionUid\":\"41ae6b36-0473-4b9c-bf2a-f536ad06f7ab\",\"startDate\":\"2026-05-20\",\"endDate\":\"2026-05-21\",\"resourceId\":-2147475036,\"resourceLocationId\":-2147483600,\"status\":0}}],\"resourceNonSpecificBlockers\":[],\"resourceZoneBlockers\":[],\"resourceZoneEntryBlockers\":[],\"waitlistApplications\":[],\"shopper\":{\"shopperUid\":\"39880c83-f551-4684-bb50-6777e533af82\",\"currentVersion\":{\"completedDate\":\"2026-01-23T04:20:46.157Z\",\"firstName\":\"DANIEL\",\"lastName\":\"SHAVER\",\"email\":\"dan.shaver@gmail.com\",\"communicationPreferences\":[{\"channel\":0,\"context\":0,\"consentGranted\":false},{\"channel\":1,\"context\":1,\"consentGranted\":false}],\"preferredCultureName\":\"en-CA\",\"flaggedStartDate\":null,\"flaggedEndDate\":null,\"vehicles\":[],\"boats\":[],\"phoneNumbers\":{\"primaryPhoneNumber\":\"+14162004476\",\"primaryCountryCode\":\"CA\",\"secondaryPhoneNumber\":null,\"secondaryCountryCode\":null},\"contact\":{\"contactName\":\"\",\"phoneNumberCountryCode\":null,\"phoneNumber\":\"\",\"email\":\"\"},\"addresses\":[{\"description\":\"Home\",\"unit\":null,\"streetAddress\":\"525 Indian Road\",\"city\":\"TORONTO\",\"region\":\"ON\",\"regionCode\":\"M5P0A3\",\"country\":\"Canada\"}],\"defaultSubEquipmentCategoryId\":-32768,\"defaultRateCategoryId\":-32768,\"defaultPassNumber\":\"\",\"defaultPassExpiryDate\":null,\"allowedRestrictedRateCategories\":[],\"disallowedPublicRateCategories\":[]},\"newVersion\":null,\"history\":[{\"completedDate\":\"2019-03-08T14:14:34.230Z\",\"firstName\":\"DANIEL\",\"lastName\":\"SHAVER\",\"email\":\"dan.shaver@gmail.com\",\"communicationPreferences\":[{\"channel\":0,\"context\":0,\"consentGranted\":false}],\"preferredCultureName\":\"en-CA\",\"flaggedStartDate\":null,\"flaggedEndDate\":null,\"vehicles\":[],\"boats\":[],\"phoneNumbers\":{\"primaryPhoneNumber\":\"4162004476\",\"primaryCountryCode\":null,\"secondaryPhoneNumber\":null,\"secondaryCountryCode\":null},\"contact\":{\"contactName\":\"\",\"phoneNumberCountryCode\":null,\"phoneNumber\":\"\",\"email\":\"\"},\"addresses\":[{\"description\":\"Home\",\"unit\":null,\"streetAddress\":\"810-60 BERWICK AVENUE\",\"city\":\"TORONTO\",\"region\":\"ON\",\"regionCode\":\"M5P0A3\",\"country\":\"Canada\"}],\"defaultSubEquipmentCategoryId\":null,\"defaultRateCategoryId\":-32768,\"defaultPassNumber\":\"\",\"defaultPassExpiryDate\":null,\"allowedRestrictedRateCategories\":[],\"disallowedPublicRateCategories\":[]},{\"completedDate\":\"2019-03-09T12:02:23.377Z\",\"firstName\":\"DANIEL\",\"lastName\":\"SHAVER\",\"email\":\"dan.shaver@gmail.com\",\"communicationPreferences\":[{\"channel\":0,\"context\":0,\"consentGranted\":false}],\"preferredCultureName\":\"en-CA\",\"flaggedStartDate\":null,\"flaggedEndDate\":null,\"vehicles\":[],\"boats\":[],\"phoneNumbers\":{\"primaryPhoneNumber\":\"+14162004476\",\"primaryCountryCode\":\"CA\",\"secondaryPhoneNumber\":null,\"secondaryCountryCode\":null},\"contact\":{\"contactName\":\"\",\"phoneNumberCountryCode\":null,\"phoneNumber\":\"\",\"email\":\"\"},\"addresses\":[{\"description\":\"Home\",\"unit\":null,\"streetAddress\":\"810-60 BERWICK AVENUE\",\"city\":\"TORONTO\",\"region\":\"ON\",\"regionCode\":\"M5P0A3\",\"country\":\"Canada\"}],\"defaultSubEquipmentCategoryId\":null,\"defaultRateCategoryId\":-32768,\"defaultPassNumber\":\"\",\"defaultPassExpiryDate\":null,\"allowedRestrictedRateCategories\":[],\"disallowedPublicRateCategories\":[]},{\"completedDate\":\"2023-03-28T19:53:17.560Z\",\"firstName\":\"DANIEL\",\"lastName\":\"SHAVER\",\"email\":\"dan.shaver@gmail.com\",\"communicationPreferences\":[{\"channel\":0,\"context\":0,\"consentGranted\":false}],\"preferredCultureName\":\"en-CA\",\"flaggedStartDate\":null,\"flaggedEndDate\":null,\"vehicles\":[],\"boats\":[],\"phoneNumbers\":{\"primaryPhoneNumber\":\"+14162004476\",\"primaryCountryCode\":\"CA\",\"secondaryPhoneNumber\":null,\"secondaryCountryCode\":null},\"contact\":{\"contactName\":\"\",\"phoneNumberCountryCode\":null,\"phoneNumber\":\"\",\"email\":\"\"},\"addresses\":[{\"description\":\"Home\",\"unit\":null,\"streetAddress\":\"410-60 Berwick Avenue\",\"city\":\"TORONTO\",\"region\":\"ON\",\"regionCode\":\"M5P0A3\",\"country\":\"Canada\"}],\"defaultSubEquipmentCategoryId\":null,\"defaultRateCategoryId\":-32768,\"defaultPassNumber\":\"\",\"defaultPassExpiryDate\":null,\"allowedRestrictedRateCategories\":[],\"disallowedPublicRateCategories\":[]},{\"completedDate\":\"2025-03-11T11:05:18.063Z\",\"firstName\":\"DANIEL\",\"lastName\":\"SHAVER\",\"email\":\"dan.shaver@gmail.com\",\"communicationPreferences\":[{\"channel\":0,\"context\":0,\"consentGranted\":false},{\"channel\":1,\"context\":1,\"consentGranted\":false}],\"preferredCultureName\":\"en-CA\",\"flaggedStartDate\":null,\"flaggedEndDate\":null,\"vehicles\":[],\"boats\":[],\"phoneNumbers\":{\"primaryPhoneNumber\":\"+14162004476\",\"primaryCountryCode\":\"CA\",\"secondaryPhoneNumber\":null,\"secondaryCountryCode\":null},\"contact\":{\"contactName\":\"\",\"phoneNumberCountryCode\":null,\"phoneNumber\":\"\",\"email\":\"\"},\"addresses\":[{\"description\":\"Home\",\"unit\":null,\"streetAddress\":\"525 Indian Road\",\"city\":\"TORONTO\",\"region\":\"ON\",\"regionCode\":\"M5P0A3\",\"country\":\"Canada\"}],\"defaultSubEquipmentCategoryId\":null,\"defaultRateCategoryId\":-32768,\"defaultPassNumber\":\"\",\"defaultPassExpiryDate\":null,\"allowedRestrictedRateCategories\":[],\"disallowedPublicRateCategories\":[]},{\"completedDate\":\"2026-01-23T04:20:46.157Z\",\"firstName\":\"DANIEL\",\"lastName\":\"SHAVER\",\"email\":\"dan.shaver@gmail.com\",\"communicationPreferences\":[{\"channel\":0,\"context\":0,\"consentGranted\":false},{\"channel\":1,\"context\":1,\"consentGranted\":false}],\"preferredCultureName\":\"en-CA\",\"flaggedStartDate\":null,\"flaggedEndDate\":null,\"vehicles\":[],\"boats\":[],\"phoneNumbers\":{\"primaryPhoneNumber\":\"+14162004476\",\"primaryCountryCode\":\"CA\",\"secondaryPhoneNumber\":null,\"secondaryCountryCode\":null},\"contact\":{\"contactName\":\"\",\"phoneNumberCountryCode\":null,\"phoneNumber\":\"\",\"email\":\"\"},\"addresses\":[{\"description\":\"Home\",\"unit\":null,\"streetAddress\":\"525 Indian Road\",\"city\":\"TORONTO\",\"region\":\"ON\",\"regionCode\":\"M5P0A3\",\"country\":\"Canada\"}],\"defaultSubEquipmentCategoryId\":-32768,\"defaultRateCategoryId\":-32768,\"defaultPassNumber\":\"\",\"defaultPassExpiryDate\":null,\"allowedRestrictedRateCategories\":[],\"disallowedPublicRateCategories\":[]}],\"hasWebAccount\":true}}}'"
)

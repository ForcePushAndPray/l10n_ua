-- disable monobank payment provider
UPDATE payment_provider
   SET mono_token = NULL;

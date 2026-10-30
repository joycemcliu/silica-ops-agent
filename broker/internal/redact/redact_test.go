package redact

import (
	"strings"
	"sync"
	"testing"
)

func TestBaseline(t *testing.T) {
	r, err := New(nil)
	if err != nil {
		t.Fatal(err)
	}
	cases := []struct{ input, forbidden string }{
		{"password=hunter-synthetic", "hunter-synthetic"},
		{`{"password":"synthetic with spaces"}`, "synthetic with spaces"},
		{"PASSWORD = 'synthetic secret'", "synthetic secret"},
		{"Authorization: Bearer synthetic-bearer", "synthetic-bearer"},
		{"api_key=synthetic-key", "synthetic-key"},
		{"access-key: synthetic-access", "synthetic-access"},
		{"postgresql://test:synthetic@db.invalid/test?sslmode=require", "synthetic"},
		{"Server=db.invalid;User=test;Password=synthetic-sql;", "synthetic-sql"},
		{"operator@example.invalid", "operator@example.invalid"},
		{"call +1 202-555-0199", "202-555-0199"},
		{"call +442079460000", "+442079460000"},
		{"call 2025550199", "2025550199"},
		{"-----BEGIN OPENSSH PRIVATE KEY-----\nsynthetic-private\n-----END OPENSSH PRIVATE KEY-----", "synthetic-private"},
		{"-----BEGIN RSA PRIVATE KEY-----\nsynthetic-truncated", "synthetic-truncated"},
		{"eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyIjoiYSJ9.c3ludGhldGlj", "eyJhbGci"},
	}
	for _, tc := range cases {
		t.Run(tc.forbidden, func(t *testing.T) {
			output := r.String(tc.input)
			if strings.Contains(output, tc.forbidden) || !strings.Contains(output, Replacement) {
				t.Fatalf("not redacted: %q", output)
			}
		})
	}
	if r.String("unit=test.service status=healthy") != "unit=test.service status=healthy" {
		t.Fatal("ordinary evidence changed")
	}
}

func TestConfigAndLiteralValues(t *testing.T) {
	r, err := Load(strings.NewReader("rules:\n  - name: local\n    pattern: 'CUSTOM_[0-9]+'\n"))
	if err != nil {
		t.Fatal(err)
	}
	r.AddSecret("synthetic")
	r.AddSecret("synthetic-longer")
	if got := r.String("synthetic-longer CUSTOM_123 password=abc"); strings.Contains(got, "longer") || strings.Contains(got, "CUSTOM") || strings.Contains(got, "abc") {
		t.Fatal(got)
	}
	for _, input := range []string{"extra: true", "rules:\n - name: bad\n   pattern: '['", "rules:\n - name: bad\n   pattern: '.*'"} {
		if _, err := Load(strings.NewReader(input)); err == nil {
			t.Fatal("invalid config accepted")
		}
	}
}

func TestConcurrentRegistrationAndUse(t *testing.T) {
	r, _ := New(nil)
	var wg sync.WaitGroup
	for range 20 {
		wg.Go(func() {
			for range 20 {
				r.AddSecret("synthetic-secret")
				r.String("password=synthetic-secret")
			}
		})
	}
	wg.Wait()
}

package session

import (
	"testing"
	"time"
)

func TestSessionLifecycleAndIdentity(t *testing.T) {
	now := time.Date(2026, 10, 30, 12, 0, 0, 0, time.UTC)
	c, err := New("user-a", "test-a", Diagnose, time.Hour, now)
	if err != nil {
		t.Fatal(err)
	}
	other, _ := New("user-a", "test-a", Diagnose, time.Hour, now)
	if c.ID == other.ID {
		t.Fatal("session IDs reused")
	}
	if err := c.Validate(now.Add(time.Hour - time.Second)); err != nil {
		t.Fatal(err)
	}
	if c.Validate(now.Add(time.Hour)) == nil {
		t.Fatal("expired session accepted")
	}
	if c.Validate(now.Add(-time.Second)) == nil {
		t.Fatal("future issued session accepted")
	}
	if c.MatchIdentity("user-a") != nil || c.MatchIdentity("user-b") == nil || c.MatchIdentity("") == nil {
		t.Fatal("identity mismatch accepted")
	}
}

func TestInvalidClaimsAndTTL(t *testing.T) {
	now := time.Now()
	for _, ttl := range []time.Duration{0, -time.Second, time.Millisecond, MaxTTL + time.Second} {
		if _, err := New("user-a", "test-a", Diagnose, ttl, now); err == nil {
			t.Fatal("invalid TTL accepted")
		}
	}
	for _, mutate := range []func(*Claims){
		func(c *Claims) { c.ID = "" }, func(c *Claims) { c.User = "" },
		func(c *Claims) { c.Env = "test-a;test-b" }, func(c *Claims) { c.Role = "solver" },
		func(c *Claims) { c.Role = "admin" }, func(c *Claims) { c.ExpiresAt = c.IssuedAt },
		func(c *Claims) { c.ExpiresAt += int64(MaxTTL / time.Second) },
	} {
		c, _ := New("user-a", "test-a", Diagnose, time.Hour, now)
		mutate(&c)
		if c.Validate(now) == nil {
			t.Fatal("invalid claims accepted")
		}
	}
}

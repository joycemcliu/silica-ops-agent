// Package session defines and validates the broker's identity boundary.
// Transport code must obtain Claims through a cryptographic Verifier, never
// unmarshal caller-supplied JSON directly into trusted claims.
package session

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"regexp"
	"time"
)

const (
	Diagnose  = "diagnose"
	Knowledge = "knowledge"
	MaxTTL    = 8 * time.Hour
)

type Claims struct {
	ID        string `json:"session"`
	User      string `json:"user"`
	Env       string `json:"env"`
	Role      string `json:"role"`
	IssuedAt  int64  `json:"iat"`
	ExpiresAt int64  `json:"exp"`
}

// Verifier implementations must verify the signature before inspecting claims,
// require a fixed algorithm, and call Claims.Validate before returning success.
// Signing implementation is pending the deployment key-model decision.
type Verifier interface {
	Verify(token string) (Claims, error)
}

var identity = regexp.MustCompile(`^[a-zA-Z0-9][a-zA-Z0-9_.@:-]{0,127}$`)

func New(user, env, role string, ttl time.Duration, now time.Time) (Claims, error) {
	if ttl < time.Second || ttl > MaxTTL {
		return Claims{}, errors.New("session TTL must be between one second and eight hours")
	}
	id := make([]byte, 16)
	if _, err := rand.Read(id); err != nil {
		return Claims{}, errors.New("cannot generate session ID")
	}
	claims := Claims{
		ID: hex.EncodeToString(id), User: user, Env: env, Role: role,
		IssuedAt: now.Unix(), ExpiresAt: now.Add(ttl).Unix(),
	}
	if err := claims.Validate(now); err != nil {
		return Claims{}, err
	}
	return claims, nil
}

func (c Claims) Validate(now time.Time) error {
	if !identity.MatchString(c.ID) || !identity.MatchString(c.User) || !identity.MatchString(c.Env) ||
		(c.Role != Diagnose && c.Role != Knowledge) || c.IssuedAt <= 0 ||
		c.ExpiresAt <= c.IssuedAt || c.ExpiresAt-c.IssuedAt > int64(MaxTTL/time.Second) ||
		c.IssuedAt > now.Unix() || c.ExpiresAt <= now.Unix() {
		return errors.New("invalid or expired session")
	}
	return nil
}

// MatchIdentity prevents a trusted gateway from attaching another user's token
// to an otherwise valid request. Caller identity must come from the gateway's
// verified identity, never from tool arguments.
func (c Claims) MatchIdentity(user string) error {
	if user == "" || c.User != user {
		return errors.New("session identity mismatch")
	}
	return nil
}

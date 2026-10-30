// Package redact sanitizes untrusted data before it crosses the broker boundary.
package redact

import (
	"errors"
	"io"
	"regexp"
	"sort"
	"strings"
	"sync"

	"ops-agent/broker/internal/config"
)

const Replacement = "[REDACTED]"

type Rule struct {
	Name    string `yaml:"name"`
	Pattern string `yaml:"pattern"`
}

type Redactor struct {
	patterns []*regexp.Regexp
	mu       sync.RWMutex
	secrets  []string
}

// Baseline rules cannot be disabled by configuration. Config adds local rules.
var baseline = []Rule{
	{"private-key", `(?s)-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----.*?(?:-----END (?:[A-Z0-9]+ )*PRIVATE KEY-----|$)`},
	{"bearer", `(?i)\bBearer\s+[^\s"'<>]+`},
	{"credential", `(?i)["']?(?:password|passwd|pwd|token|secret|api[_-]?key|access[_-]?key|client[_-]?secret|authorization|cookie|set-cookie)["']?\s*[:=]\s*(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;}]+)`},
	{"connection-uri", `(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqps?|mssql|sqlserver)://[^\s"'<>]+`},
	{"email", `(?i)\b[a-z0-9.!#$%&'*+/=?^_` + "`" + `{|}~-]+@[a-z0-9.-]+\.[a-z]{2,}\b`},
	{"phone", `(?:\+\d{1,3}[ .-]?)?(?:\(\d{3}\)|\b\d{3})[ .-]\d{3}[ .-]\d{4}\b`},
	{"international-phone", `\+[1-9]\d{7,14}\b`},
	{"compact-phone", `\b[2-9]\d{2}[2-9]\d{6}\b`},
	{"jwt", `\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b`},
}

func New(additional []Rule) (*Redactor, error) {
	r := &Redactor{}
	for _, rule := range append(append([]Rule{}, baseline...), additional...) {
		if rule.Name == "" || rule.Pattern == "" {
			return nil, errors.New("redaction rules need a name and a pattern")
		}
		pattern, err := regexp.Compile(rule.Pattern)
		if err != nil || pattern.MatchString("") {
			return nil, errors.New("invalid redaction pattern")
		}
		r.patterns = append(r.patterns, pattern)
	}
	return r, nil
}

func Load(reader io.Reader) (*Redactor, error) {
	var doc struct {
		Rules []Rule `yaml:"rules"`
	}
	if err := config.Decode(reader, &doc); err != nil {
		return nil, err
	}
	return New(doc.Rules)
}

// AddSecret registers literal values (including unlabelled passwords) before
// any use. Do not rely on pattern matching for known credential material.
func (r *Redactor) AddSecret(value string) {
	if value == "" {
		return
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	for _, existing := range r.secrets {
		if existing == value {
			return
		}
	}
	r.secrets = append(r.secrets, value)
	// Replace long values before short substrings of the same credential.
	sort.Slice(r.secrets, func(i, j int) bool { return len(r.secrets[i]) > len(r.secrets[j]) })
}

func (r *Redactor) String(value string) string {
	r.mu.RLock()
	for _, secret := range r.secrets {
		value = strings.ReplaceAll(value, secret, Replacement)
	}
	r.mu.RUnlock()
	for _, pattern := range r.patterns {
		value = pattern.ReplaceAllString(value, Replacement)
	}
	return value
}

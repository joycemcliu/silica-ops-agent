package main

import (
	"bytes"
	"io"
	"strings"
	"testing"
)

func TestExampleConfiguration(t *testing.T) {
	var out bytes.Buffer
	err := run([]string{"check-config", "--environments", "../../../environments/envs.yaml", "--access", "../../../environments/access.yaml", "--redaction", "../../../environments/redaction.yaml"}, &out, io.Discard)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.String(), "1 environment(s)") {
		t.Fatal(out.String())
	}
}

func TestInvalidArgumentsDoNotEchoSecrets(t *testing.T) {
	for _, args := range [][]string{nil, {"serve"}, {"check-config"}, {"check-config", "--password=synthetic-secret"}} {
		err := run(args, io.Discard, io.Discard)
		if err == nil || strings.Contains(err.Error(), "synthetic-secret") {
			t.Fatal("unsafe argument handling")
		}
	}
}

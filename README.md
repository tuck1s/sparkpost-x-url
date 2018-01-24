# Sparkpost-x-url

Extends the SparkPost template language (via external this external utility) with external data-source url accesses.

## Usage
The handlebars syntax is extended using the form

```
    {{x-url get url}}
```

Nested handlebar expressions are allowed.  The intention is to allow replacement of any part of the request to be derived from existing substitution variables
e.g.
```html
   {{x-url get https://blah.com?{{foo}}                     <!-- this includes a personalisation query param>
```

Variable references within `x-url` can nest and include array refs, like SparkPost e.g.
```
{{foo}}
{{foo.bar}}
{{foo[idx]}}                                                # JSON arrays are zero-based so 0<= idx < len
{{foo[idx].bar}}
:
etc
```

```html
   {{x-url get https://blah.com?{{foo.bar}} }}              <!-- this is a nested variable reference> 
   {{x-url get https://blah.com?{{foo.{{bar}} }} }}         <!-- this is a nested indirect variable reference>
   {{x-url {{foo}} }}                                       <!-- this gets the whole request from a var>
```

You could even have a url return a url if you really wanted to, although that's a recipe for slowness.
```html
   {{x-url {{x-url {{foo}} }} }}
```

## Substitution variables within `x-url`

Substitution variable values within the `x-url` expression e.g. `{{foo}}` are sought with precedence

- Per-recipient `substitution_data`
- Per-recipient `metadata`
- Global (transmission level) `substitution_data`
- Global (transmission level) `metadata`

## Examples

Template making example use of [OneSpot](https://www.onespot.com/) content personalisation service is included in [heml](https://heml.io) format.

## See also

[SparkPost API docs - Substitutions Reference](https://developers.sparkpost.com/api/substitutions-reference.html)

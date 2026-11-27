# Round 62: the page change the core track needs for the Seal of Flames Children row (F-049)

**Done:** applied by the round-62 assemble step as patches/zakuro/0029 (`rows_for`, `fit_game`: the form is made again when the game changes; test `a_row_grey_for_a_game_is_fixed_there`). Built into play/game (build/r62/FINAL_SHA.txt).

The owner said "seal children being out is fine". `rando.py schema` now gives the Children row
`"grey_for": {"seal": "no child in Seal of Flames"}` (tools/randomizer/ingame.py GREY_FOR). The randomizer already
protects itself: `rando.py make --game seal` never turns Children on, so even an unchanged page cannot lay children
in a Seal run. Only the look needs the page.

The exact change in `engine/zakuro/crates/zakuro/src/rando_page.rs` (core track's own copy, build/r62/core/):

1. `struct Row`: add the field
   ```rust
   /// round 62: games this row cannot be used in -> the reason (shown grey at its default there).
   pub grey_for: std::collections::BTreeMap<String, String>,
   ```
2. `parse_schema`, in the `out.push(Row { .. })`: add
   ```rust
   grey_for: row.get("grey_for").and_then(Value::as_object).map(|m| m.iter()
       .filter_map(|(k, v)| v.as_str().map(|s| (k.clone(), s.to_owned()))).collect()).unwrap_or_default(),
   ```
3. Where the page builds its form for a game (`RandoForm::new(found.rows.clone())` in `poll`, and wherever
   `self.game` is set for the page that opens), apply the game before the form is made:
   ```rust
   fn rows_for(rows: &[Row], game: Option<&str>) -> Vec<Row> {
       rows.iter().cloned().map(|mut row| {
           if let Some(why) = game.and_then(|g| row.grey_for.get(g)) {
               row.fixed = true;
               row.all = row.default.clone();
               row.label = format!("{} ({why})", row.label);
           }
           row
       }).collect()
   }
   ```
   and use `RandoForm::new(rows_for(&found.rows, self.game.as_deref()))`. If the form is kept between games, make it
   again when the game changes (Fates <-> Seal).
4. Test (beside the existing schema tests at the end of the file): a schema with
   `"grey_for": {"seal": "x"}` on Children gives `fixed == false` for `None` (Fates) and `fixed == true`, default value
   and label suffix " (x)" for `Some("seal")`. "Everything on" leaves the row at its default for Seal.

With this change, Fates is untouched: no row has `grey_for` for `fates`. A new answer key is not added, so run ids
do not change because of this row.

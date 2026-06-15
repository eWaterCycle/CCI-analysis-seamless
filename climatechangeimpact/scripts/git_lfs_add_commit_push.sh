#!/bin/bash
DIR_PARENT=climatechangeimpact/regions
BATCH=100

for country in australia austria brazil chile czech_republic england germany \
               lichtenstein mexico scotland switzerland wales canada \
               united_states_of_america; do
    DIR="$DIR_PARENT/$country"
    [ -d "$DIR" ] || continue

    TOTAL=$(ls "$DIR/" | wc -l)
    if [ "$TOTAL" -le "$BATCH" ]; then
        git add "$DIR/"
        git commit -m "Update analysis: $country" 2>/dev/null \
            || echo "(no changes for $country)"
    else
        for start in $(seq 1 $BATCH $TOTAL); do
            end=$((start + BATCH - 1))
            [ $end -gt $TOTAL ] && end=$TOTAL
            ls "$DIR/" | sort | sed -n "${start},${end}p" \
                | xargs -I{} git add "$DIR/{}"
            git commit -m "Update analysis: $country $start-$end" 2>/dev/null \
                || echo "(no changes for $country $start-$end)"
        done
    fi
done

git add -A
git commit -m "Update analysis: remaining" 2>/dev/null || echo "(nothing left)"

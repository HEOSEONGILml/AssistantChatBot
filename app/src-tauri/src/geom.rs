#[derive(Clone, Copy, Debug, PartialEq, serde::Deserialize)]
pub struct Rect { pub left: i32, pub top: i32, pub right: i32, pub bottom: i32 }

impl Rect {
    pub fn intersects(&self, o: &Rect) -> bool {
        self.left < o.right && o.left < self.right && self.top < o.bottom && o.top < self.bottom
    }
}

pub fn covered(region: &Rect, above: &[Rect]) -> bool {
    above.iter().any(|w| w.intersects(region))
}

#[cfg(test)]
mod tests {
    use super::*;
    const R: Rect = Rect { left: 10, top: 10, right: 20, bottom: 20 };

    #[test]
    fn intersects_overlap_but_not_touching() {
        assert!(R.intersects(&Rect { left: 15, top: 15, right: 30, bottom: 30 }));
        assert!(!R.intersects(&Rect { left: 20, top: 10, right: 30, bottom: 20 }));
    }

    #[test]
    fn covered_only_when_some_window_above_overlaps() {
        assert!(!covered(&R, &[]));
        assert!(!covered(&R, &[Rect { left: 30, top: 30, right: 40, bottom: 40 }]));
        assert!(covered(&R, &[Rect { left: 30, top: 30, right: 40, bottom: 40 }, Rect { left: 0, top: 0, right: 12, bottom: 12 }]));
    }
}

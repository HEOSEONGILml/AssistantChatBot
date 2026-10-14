#[derive(Clone, Copy, Debug, PartialEq, serde::Deserialize)]
pub struct Rect { pub left: i32, pub top: i32, pub right: i32, pub bottom: i32 }

impl Rect {
    pub fn contains(&self, x: i32, y: i32) -> bool {
        x >= self.left && x < self.right && y >= self.top && y < self.bottom
    }
    pub fn intersects(&self, o: &Rect) -> bool {
        self.left < o.right && o.left < self.right && self.top < o.bottom && o.top < self.bottom
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const R: Rect = Rect { left: 10, top: 10, right: 20, bottom: 20 };

    #[test]
    fn contains_inside_and_edges() {
        assert!(R.contains(10, 10));
        assert!(R.contains(19, 19));
        assert!(!R.contains(20, 20)); // right/bottom 은 포함하지 않는다
        assert!(!R.contains(9, 15));
    }

    #[test]
    fn intersects_overlap_and_touching() {
        assert!(R.intersects(&Rect { left: 15, top: 15, right: 30, bottom: 30 }));
        assert!(!R.intersects(&Rect { left: 20, top: 10, right: 30, bottom: 20 })); // 맞닿기만 함
        assert!(!R.intersects(&Rect { left: 0, top: 0, right: 5, bottom: 5 }));
    }
}
